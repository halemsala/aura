using System.Diagnostics;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;

namespace Aura.QuantX.Desktop;

public sealed class ServiceSupervisor : IAsyncDisposable
{
    private readonly string _root;
    private readonly DesktopConfig _config;
    private readonly HttpClient _http = new() { Timeout = TimeSpan.FromSeconds(8) };
    private readonly List<Process> _children = new();
    private readonly object _lock = new();
    // V25: lock dedicado ao log
    private readonly object _logLock = new();
    private readonly string _logPath;
    // V25: backoff Equal Jitter
    private readonly BackoffPolicy _backoff = new(baseMs: 1000, capMs: 30000, resetAfterStableMs: 60000);
    private const string MonitorStatusUrl = "http://127.0.0.1:8765/api/status";

    public ServiceSupervisor(string root, DesktopConfig config)
    {
        _root = Path.GetFullPath(root);
        _config = config;
        var logDir = Path.Combine(_root, "logs_instalacao");
        Directory.CreateDirectory(logDir);
        _logPath = Path.Combine(logDir, "desktop_host.log");
    }

    public string LogPath => _logPath;

    public async Task<IReadOnlyList<ServiceStatus>> StartAllAsync(CancellationToken cancellationToken = default)
    {
        var result = new List<ServiceStatus>();
        foreach (var service in _config.Services.Where(s => s.Enabled))
        {
            cancellationToken.ThrowIfCancellationRequested();
            result.Add(await EnsureServiceAsync(service, cancellationToken));
        }
        return result;
    }

    public async Task<ServiceStatus> EnsureServiceAsync(ServiceConfig service, CancellationToken cancellationToken = default)
    {
        var before = await CheckHealthAsync(service, cancellationToken);
        if (before.Healthy)
        {
            WriteLog($"{service.Name}: já estava saudável em {service.HealthUrl}; nenhuma segunda instância foi iniciada.");
            return before with { Detail = "já estava ativo; processo existente preservado" };
        }

        var python = ResolvePath(service.Python);
        var script = ResolvePath(service.Script);
        var workingDirectory = ResolvePath(service.WorkingDirectory);
        if (!File.Exists(python))
            return new ServiceStatus(service.Name, service.Port, service.HealthUrl, false, $"Python da venv ausente: {python}");
        if (!File.Exists(script))
            return new ServiceStatus(service.Name, service.Port, service.HealthUrl, false, $"script ausente: {script}");

        var startInfo = new ProcessStartInfo
        {
            FileName = python,
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
        };
        startInfo.Environment["CORNERAI_OLLAMA_HOST"] = _config.Ollama.BaseUrl;
        startInfo.Environment["CORNERAI_CHAT_MODEL"] = _config.Ollama.Model;
        startInfo.Environment["CORNERAI_ADMIN_MODEL"] = _config.Ollama.Model;
        startInfo.Environment["CORNERAI_CHAT_TIMEOUT"] = "120";
        startInfo.Environment["PYTHONUNBUFFERED"] = "1";
        startInfo.Environment["PYTHONUTF8"] = "1";
        startInfo.Environment["PAPER_TRADE"] = "true";
        startInfo.Environment["EXECUTION_ALLOWED"] = "false";
        startInfo.Environment["AURA_PAPER_TRADE"] = "1";
        startInfo.Environment["AURA_EXECUTION_ALLOWED"] = "0";
        startInfo.Environment["AURA_UNLOCK_LIVE"] = "0";
        startInfo.Environment["GLM_ADVISORY_ONLY"] = "true";
        // Propaga token para Bridge/Engine/Voice (senão Bridge exige auth e feed falha)
        var bridgeToken = Environment.GetEnvironmentVariable("CORNERAI_BRIDGE_TOKEN");
        if (!string.IsNullOrWhiteSpace(bridgeToken))
        {
            startInfo.Environment["CORNERAI_BRIDGE_TOKEN"] = bridgeToken;
            startInfo.Environment["CORNERAI_BRIDGE_REQUIRE_TOKEN"] = "1";
        }
        startInfo.ArgumentList.Add(script);
        foreach (var argument in service.Arguments)
            startInfo.ArgumentList.Add(argument);

        try
        {
            var process = new Process { StartInfo = startInfo, EnableRaisingEvents = true };
            process.OutputDataReceived += (_, e) => { if (e.Data is not null) WriteLog($"{service.Name} stdout: {e.Data}"); };
            process.ErrorDataReceived += (_, e) => { if (e.Data is not null) WriteLog($"{service.Name} stderr: {e.Data}"); };
            process.Exited += (_, _) =>
            {
                WriteLog($"{service.Name}: processo encerrou com código {process.ExitCode}.");
                lock (_lock) _children.Remove(process);
            };
            if (!process.Start())
                return new ServiceStatus(service.Name, service.Port, service.HealthUrl, false, "Process.Start retornou false");
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();
            lock (_lock) _children.Add(process);
            WriteLog($"{service.Name}: iniciado com PID {process.Id}; aguardando {service.HealthUrl}.");
        }
        catch (Exception ex)
        {
            WriteLog($"{service.Name}: falha ao iniciar: {ex.Message}");
            return new ServiceStatus(service.Name, service.Port, service.HealthUrl, false, ex.Message);
        }

        var deadline = DateTimeOffset.UtcNow.AddSeconds(60);
        while (DateTimeOffset.UtcNow < deadline)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var status = await CheckHealthAsync(service, cancellationToken);
            if (status.Healthy)
            {
                WriteLog($"{service.Name}: health check aprovado.");
                return status with { Detail = "iniciado e saudável" };
            }
            await Task.Delay(1000, cancellationToken);
        }

        var final = await CheckHealthAsync(service, cancellationToken);
        return final with { Detail = final.Detail == "offline" ? "timeout de 60s no health check; consulte desktop_host.log" : final.Detail };
    }

    public async Task<ServiceStatus> CheckHealthAsync(ServiceConfig service, CancellationToken cancellationToken = default)
    {
        try
        {
            using var response = await _http.GetAsync(service.HealthUrl, cancellationToken);
            if (response.IsSuccessStatusCode)
                return new ServiceStatus(service.Name, service.Port, service.HealthUrl, true, $"HTTP {(int)response.StatusCode}");
            return new ServiceStatus(service.Name, service.Port, service.HealthUrl, false, $"HTTP {(int)response.StatusCode}");
        }
        catch (TaskCanceledException)
        {
            return new ServiceStatus(service.Name, service.Port, service.HealthUrl, false, "timeout/offline");
        }
        catch (HttpRequestException ex)
        {
            return new ServiceStatus(service.Name, service.Port, service.HealthUrl, false, ex.Message);
        }
    }

    public async Task<(bool Reachable, bool ModelPresent, string Detail)> CheckOllamaAsync(CancellationToken cancellationToken = default)
    {
        var tagsUrl = _config.Ollama.BaseUrl.TrimEnd('/') + "/api/tags";
        try
        {
            using var response = await _http.GetAsync(tagsUrl, cancellationToken);
            var body = await response.Content.ReadAsStringAsync(cancellationToken);
            if (!response.IsSuccessStatusCode)
                return (true, false, $"Ollama respondeu HTTP {(int)response.StatusCode}");
            using var json = JsonDocument.Parse(body);
            var names = json.RootElement.TryGetProperty("models", out var models)
                ? models.EnumerateArray().Select(x => x.TryGetProperty("name", out var n) ? n.GetString() : null).Where(x => x is not null).ToList()
                : new List<string?>();
            var present = names.Any(x => string.Equals(x, _config.Ollama.Model, StringComparison.OrdinalIgnoreCase));
            return (true, present, present ? $"modelo {_config.Ollama.Model} presente" : $"modelo {_config.Ollama.Model} ausente; disponíveis: {string.Join(", ", names)}");
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or JsonException)
        {
            return (false, false, $"Ollama offline: {ex.Message}");
        }
    }

    public Task<(bool Reachable, bool ModelPresent, string Detail)> EnsureOllamaAsync(CancellationToken cancellationToken = default)
    {
        // Compatibilidade de API: o Desktop somente consulta Ollama; nunca inicia processos.
        return CheckOllamaAsync(cancellationToken);
    }

    public string ResolvePath(string relativeOrAbsolute)
    {
        var expanded = Environment.ExpandEnvironmentVariables(relativeOrAbsolute.Replace('/', Path.DirectorySeparatorChar));
        return Path.IsPathRooted(expanded) ? expanded : Path.GetFullPath(expanded, _root);
    }

    private void WriteLog(string line)
    {
        var text = $"[{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss zzz}] {line}{Environment.NewLine}";
        lock (_logLock)
        {
            try { File.AppendAllText(_logPath, text, Encoding.UTF8); }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }
    }

    public ValueTask DisposeAsync()
    {
        lock (_lock)
        {
            foreach (var process in _children)
            {
                try { process.Dispose(); } catch { }
            }
            _children.Clear();
        }
        _http.Dispose();
        return ValueTask.CompletedTask;
    }

    // V25: monitor com BackoffPolicy Equal Jitter + filtro correto de OCE
    public async Task MonitorServicesAsync(CancellationToken token)
    {
        while (!token.IsCancellationRequested)
        {
            try
            {
                using var response = await _http.GetAsync(MonitorStatusUrl, token);
                if (response.IsSuccessStatusCode)
                {
                    var content = await response.Content.ReadAsStringAsync(token);
                    if (IsEngineReady(content))
                    {
                        _backoff.NotifyHealthy();
                        WriteLog("Monitor: sistemas ready");
                        try { await Task.Delay(5000, token); }
                        catch (OperationCanceledException) { break; }
                        continue;
                    }
                }
            }
            catch (OperationCanceledException) when (token.IsCancellationRequested)
            {
                break;
            }
            catch (OperationCanceledException)
            {
                // timeout interno do _http (2s): falha, nao shutdown
            }
            catch (Exception ex)
            {
                WriteLog($"Monitor: {ex.Message}");
            }

            var delayMs = _backoff.NextDelayMs();
            WriteLog($"Monitor: aguardando servicos... retry em {delayMs / 1000.0:0.0}s");
            try { await Task.Delay((int)delayMs, token); }
            catch (OperationCanceledException) { break; }
        }
    }

    private static bool IsEngineReady(string json)
    {
        // V26.3-FIX: /api/status devolve "ok"; /api/readiness devolve "ready".
        // Aceitar ambos (e "alive" de /api/health) evita backoff infinito.
        try
        {
            using var doc = JsonDocument.Parse(json);
            if (doc.RootElement.ValueKind != JsonValueKind.Object)
                return false;
            if (!doc.RootElement.TryGetProperty("status", out var status) || status.ValueKind != JsonValueKind.String)
                return false;
            var s = status.GetString() ?? "";
            if (string.Equals(s, "ready", StringComparison.OrdinalIgnoreCase)) return true;
            if (string.Equals(s, "ok", StringComparison.OrdinalIgnoreCase)) return true;
            if (string.Equals(s, "alive", StringComparison.OrdinalIgnoreCase)) return true;
            // fallback: engine=online
            if (doc.RootElement.TryGetProperty("engine", out var eng)
                && eng.ValueKind == JsonValueKind.String
                && string.Equals(eng.GetString(), "online", StringComparison.OrdinalIgnoreCase))
                return true;
            return false;
        }
        catch (JsonException)
        {
            return false;
        }
    }
}

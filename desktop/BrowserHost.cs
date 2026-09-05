using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
using System.Collections.Generic;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;

namespace Aura.QuantX.Desktop;

public sealed class BrowserHost
{
    private readonly WebView2 _view;
    private readonly string _root;
    private readonly DesktopConfig _config;
    private const string UiCacheRevision = "V37-3-21-DESKTOP-TRPC-ROOT";
    private string _captureScript = "";

    private static readonly CoreWebView2WebResourceContext[] LiteBlocked =
    {
        CoreWebView2WebResourceContext.Image,
        CoreWebView2WebResourceContext.Media,
        CoreWebView2WebResourceContext.Font,
        CoreWebView2WebResourceContext.Stylesheet,
    };
    private bool _liteMode;

    private static readonly string[] FixtureBootstrapSuffixes =
        { "", "/stats", "/events", "/timeline", "/incidents", "/preodds", "/x7", "/history" };

    private long _capturesEmitted;
    private long _blockedRequests;
    private long _bootstrapRequests;
    private CancellationTokenSource? _ramGuardCts;
    private Task? _ramGuardTask;
    private static readonly HttpClient LocalApiClient = new()
    {
        Timeout = TimeSpan.FromSeconds(20)
    };

    public event EventHandler<string>? CaptureReceived;
    public event EventHandler<string>? StatusChanged;

    public BrowserHost(WebView2 view, string root, DesktopConfig config)
    {
        _view = view;
        _root = Path.GetFullPath(root);
        _config = config;
    }

    public bool IsLiteMode => _liteMode;
    public int DiskCacheMb { get; set; } = 256;

    public async Task InitializeAsync(bool operatorShell = true)
    {
        // Pasta isolada por versão reduz cache corrompido entre releases
        var ver = string.IsNullOrWhiteSpace(_config.App.Version) ? "v25q" : _config.App.Version.Replace(' ', '_');
        var userData = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "AURA_QUANT_X",
            _config.App.UserDataFolder,
            ver);
        Directory.CreateDirectory(userData);

        try
        {
            var environment = await WebViewEnvironmentFactory.GetSharedAsync(userData, DiskCacheMb);
            await _view.EnsureCoreWebView2Async(environment);
        }
        catch (Exception ex)
        {
            throw new InvalidOperationException(
                "WebView2 Runtime não está disponível. Instale o Microsoft Edge WebView2 Runtime antes de abrir o AURA Desktop.", ex);
        }

        var core = _view.CoreWebView2;
        core.Settings.IsZoomControlEnabled = false;
        core.PermissionRequested += (_, e) =>
        {
            if (e.PermissionKind == CoreWebView2PermissionKind.Microphone ||
                e.PermissionKind == CoreWebView2PermissionKind.Camera)
            {
                e.State = CoreWebView2PermissionState.Allow;
                e.Handled = true;
            }
        };
        core.ProcessFailed += (_, e) =>
        {
            try
            {
                StatusChanged?.Invoke(this, "WebView2 ProcessFailed: " + e.ProcessFailedKind);
                // Recuperacao leve: volta a Matriz se o processo renderer cair
                if (e.ProcessFailedKind == CoreWebView2ProcessFailedKind.BrowserProcessExited ||
                    e.ProcessFailedKind == CoreWebView2ProcessFailedKind.RenderProcessExited)
                {
                    try { Navigate(_config.App.Homepage); } catch { /* ignore */ }
                }
            }
            catch { /* ignore */ }
        };
        core.WebResourceRequested += OnWebResourceRequested;
        // Filtros amplos: WebView2 por vezes nao dispara o padrao estreito /api/aura/*
        core.AddWebResourceRequestedFilter(
            $"https://{_config.App.VirtualHost}/*",
            CoreWebView2WebResourceContext.All);
        core.AddWebResourceRequestedFilter(
            $"https://{_config.App.VirtualHost}/api/*",
            CoreWebView2WebResourceContext.All);
        core.AddWebResourceRequestedFilter(
            $"https://{_config.App.VirtualHost}/api/aura/*",
            CoreWebView2WebResourceContext.All);

        var uiFolder = Path.Combine(_root, "desktop", "ui", "matriz_v22");
        if (!Directory.Exists(uiFolder))
            throw new DirectoryNotFoundException($"UI Operator OS ausente: {uiFolder}");

        core.SetVirtualHostNameToFolderMapping(
            _config.App.VirtualHost,
            uiFolder,
            CoreWebView2HostResourceAccessKind.Allow);
        await EnsureFreshUiCacheAsync(userData);

        var capturePath = Path.Combine(_root, _config.Browser.CaptureScript.Replace('/', Path.DirectorySeparatorChar));
        _captureScript = File.Exists(capturePath) ? await File.ReadAllTextAsync(capturePath) : "";
        // A captura não é registrada globalmente. Ela só é injetada em
        // NavigationCompleted depois que o host exato SokkerPRO foi validado.

        core.WebMessageReceived += OnWebMessageReceived;
        core.NavigationStarting += (_, e) =>
        {
            if (Uri.TryCreate(e.Uri, UriKind.Absolute, out var uri) && !IsAllowedNavigation(uri))
            {
                e.Cancel = true;
                StatusChanged?.Invoke(this, $"Navegação bloqueada fora das origens permitidas: {uri.Host}");
            }
        };
        core.NavigationCompleted += (_, e) =>
        {
            if (!e.IsSuccess)
            {
                StatusChanged?.Invoke(this, $"Falha de navegação: {e.WebErrorStatus}");
                return;
            }
            var host = _view.Source?.Host ?? "";
            StatusChanged?.Invoke(this, $"Página carregada: {host}");
            if (IsSokkerHost(host))
                InjectAuraCaptureAsync();
        };
        StartRamGuard();

        core.NewWindowRequested += (_, e) =>
        {
            e.Handled = true;
            var target = e.Uri ?? "";
            if (Uri.TryCreate(target, UriKind.Absolute, out var parsed) && IsAllowedNavigation(parsed))
            {
                Navigate(target);
                StatusChanged?.Invoke(this, "Popup SokkerPRO retido no AURA: " + parsed.PathAndQuery);
            }
            else
                StatusChanged?.Invoke(this, "Popup bloqueado: " + target);
        };

        if (operatorShell)
            NavigateWithFallbacks();
    }

    /// <summary>
    /// P1: tenta Homepage e depois FallbackHomepages (desktop.json), em vez de ignorar a cadeia.
    /// </summary>
    private void NavigateWithFallbacks()
    {
        var candidates = new List<string>();
        if (!string.IsNullOrWhiteSpace(_config.App.Homepage))
            candidates.Add(_config.App.Homepage);
        if (_config.App.FallbackHomepages is not null)
        {
            foreach (var u in _config.App.FallbackHomepages)
            {
                if (!string.IsNullOrWhiteSpace(u) && !candidates.Contains(u, StringComparer.OrdinalIgnoreCase))
                    candidates.Add(u);
            }
        }
        if (candidates.Count == 0)
            candidates.Add("https://aura.local/index.html");

        var first = candidates[0];
        Navigate(first);
        StatusChanged?.Invoke(this, $"Homepage: {first} (fallbacks={candidates.Count - 1})");
    }

    private async Task EnsureFreshUiCacheAsync(string userData)
    {
        var marker = Path.Combine(userData, ".ui-cache-revision");
        var previous = File.Exists(marker) ? await File.ReadAllTextAsync(marker) : "";
        if (string.Equals(previous.Trim(), UiCacheRevision, StringComparison.Ordinal)) return;
        try
        {
            await _view.CoreWebView2!.Profile.ClearBrowsingDataAsync(CoreWebView2BrowsingDataKinds.DiskCache);
            await File.WriteAllTextAsync(marker, UiCacheRevision);
            StatusChanged?.Invoke(this, "Cache da Operator OS atualizado; cookies preservados.");
        }
        catch (Exception ex)
        {
            StatusChanged?.Invoke(this, "Cache da Operator OS não pôde ser atualizado: " + ex.Message);
        }
    }

    public void SetLiteMode(bool enabled)
    {
        var core = _view.CoreWebView2;
        if (core is null)
        {
            StatusChanged?.Invoke(this, "Modo lite: WebView2 ainda não inicializado.");
            return;
        }
        foreach (var ctx in LiteBlocked)
        {
            if (enabled) core.AddWebResourceRequestedFilter("*", ctx);
            else core.RemoveWebResourceRequestedFilter("*", ctx);
        }
        _liteMode = enabled;
        StatusChanged?.Invoke(this, enabled
            ? "Modo lite ATIVO: imagens/fontes/mídia/estilos bloqueados — captura e dados intactos."
            : "Modo normal ATIVO: renderização completa.");
    }

    public async Task SuspendWhenHiddenAsync()
    {
        var core = _view.CoreWebView2;
        if (core is null || core.IsSuspended) return;
        try
        {
            var ok = await core.TrySuspendAsync();
            StatusChanged?.Invoke(this, ok
                ? "WebView2 suspenso (economia de memória)."
                : "Suspensão não aceita agora (navegação em curso).");
        }
        catch (Exception ex)
        {
            StatusChanged?.Invoke(this, "Suspensão falhou: " + ex.Message);
        }
    }

    public void ResumeAfterShown()
    {
        try
        {
            var core = _view.CoreWebView2;
            if (core is null || !core.IsSuspended) return;
            core.Resume();
            StatusChanged?.Invoke(this, "WebView2 retomado.");
        }
        catch (Exception ex)
        {
            StatusChanged?.Invoke(this, "Retomada falhou: " + ex.Message);
        }
    }

    private void StartRamGuard()
    {
        if (_ramGuardTask is not null && !_ramGuardTask.IsCompleted) return;
        _ramGuardCts?.Dispose();
        _ramGuardCts = new CancellationTokenSource();
        _ramGuardTask = RamGuardLoopAsync(_ramGuardCts.Token);
    }

    private async Task RamGuardLoopAsync(CancellationToken cancellationToken)
    {
        var interval = TimeSpan.FromHours(1);
        try
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                await Task.Delay(interval, cancellationToken).ConfigureAwait(false);
                if (cancellationToken.IsCancellationRequested) break;
                await PurgeCacheIfOlderThanAsync(TimeSpan.FromHours(24)).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException)
        {
            // Encerramento normal do host.
        }
        catch (Exception ex)
        {
            StatusChanged?.Invoke(this, "RAM Guard falhou: " + ex.Message);
        }
    }

    public async Task StopRamGuardAsync()
    {
        var cts = Interlocked.Exchange(ref _ramGuardCts, null);
        if (cts is null) return;
        cts.Cancel();
        try
        {
            if (_ramGuardTask is not null) await _ramGuardTask.ConfigureAwait(false);
        }
        catch (OperationCanceledException) { }
        finally
        {
            cts.Dispose();
            _ramGuardTask = null;
        }
    }

    private DateTime _lastCachePurgeUtc = DateTime.MinValue;

    public async Task PurgeCacheIfOlderThanAsync(TimeSpan maxAge)
    {
        if (DateTime.UtcNow - _lastCachePurgeUtc < maxAge)
        {
            StatusChanged?.Invoke(this, "Cache SokkerPRO válido (<24h) — sem purge.");
            return;
        }
        await ClearCacheAsync().ConfigureAwait(false);
        _lastCachePurgeUtc = DateTime.UtcNow;
    }

    public async Task ClearCacheAsync()
    {
        var core = _view.CoreWebView2;
        if (core is null)
        {
            StatusChanged?.Invoke(this, "Limpeza de cache: WebView2 não inicializado.");
            return;
        }
        try
        {
            await core.Profile.ClearBrowsingDataAsync(CoreWebView2BrowsingDataKinds.DiskCache);
            StatusChanged?.Invoke(this, "Cache de disco limpo — cookies de sessão preservados.");
        }
        catch (Exception ex)
        {
            StatusChanged?.Invoke(this, "Limpeza de cache falhou: " + ex.Message);
        }
    }

    public async Task<int> BootstrapFixtureAsync(string fixtureId,
        string apiHost = "https://m2.sokkerpro.com")
    {
        var core = _view.CoreWebView2;
        var currentHost = _view.Source?.Host ?? "";
        if (core is null || !IsSokkerHost(currentHost))
        {
            StatusChanged?.Invoke(this,
                "Bootstrap: requer página SokkerPRO ativa (cookies de sessão).");
            return 0;
        }
        int n = 0;
        foreach (var suffix in FixtureBootstrapSuffixes)
        {
            var url = apiHost.TrimEnd('/') + "/fixture/" +
                      Uri.EscapeDataString(fixtureId ?? "") + suffix;
            var script = "fetch(" + JsonSerializer.Serialize(url) +
                         ", {credentials:'include'})" +
                         ".then(function(){return 1;}).catch(function(){return 0;});";
            try
            {
                await core.ExecuteScriptAsync(script);
                Interlocked.Increment(ref _bootstrapRequests);
                n++;
            }
            catch (Exception ex)
            {
                StatusChanged?.Invoke(this, "Bootstrap falhou em '" + suffix + "': " + ex.Message);
            }
            await Task.Delay(150);
        }
        StatusChanged?.Invoke(this,
            "Bootstrap fixture " + fixtureId + ": " + n + " endpoints solicitados.");
        return n;
    }

    public Dictionary<string, object> Stats() => new()
    {
        ["captures_emitted"] = Interlocked.Read(ref _capturesEmitted),
        ["blocked_requests"] = Interlocked.Read(ref _blockedRequests),
        ["bootstrap_requests"] = Interlocked.Read(ref _bootstrapRequests),
        ["lite_mode"] = _liteMode,
        ["capture_script_registered"] = false,
        ["capture_injection"] = "navigation_gated_sokkerpro_only",
    };

    private async void OnWebResourceRequested(object? sender, CoreWebView2WebResourceRequestedEventArgs e)
    {
        // Sem GetDeferral o WebView2 fecha o evento no primeiro await
        // e a Operator OS cai em "Failed to fetch" / modo simulado.
        var deferral = e.GetDeferral();
        try
        {
            if (TryTrpcStub(e.Request.Uri, out var trpcPayload))
            {
                e.Response = CreateJsonResponse(200, "OK", trpcPayload);
                return;
            }
            if (TryResolveLocalApi(e.Request.Uri, out var target))
            {
                e.Response = await ForwardLocalApiAsync(e.Request, target);
                return;
            }
            if (!_liteMode) return;
            e.Response = _view.CoreWebView2!.Environment.CreateWebResourceResponse(
                null, 404, "Blocked by AURA lite mode", "");
            Interlocked.Increment(ref _blockedRequests);
        }
        catch (Exception ex)
        {
            StatusChanged?.Invoke(this, "Proxy local falhou: " + ex.Message);
            try
            {
                e.Response = CreateJsonResponse(502, "Bad Gateway", new { ok = false, error = "local_api_proxy_failed" });
            }
            catch { /* resposta já pode ter sido consumida */ }
        }
        finally
        {
            deferral.Complete();
        }
    }

    private static bool TryTrpcStub(string rawUri, out object payload)
    {
        payload = new object();
        if (!Uri.TryCreate(rawUri, UriKind.Absolute, out var source)) return false;
        if (!source.AbsolutePath.StartsWith("/api/trpc/", StringComparison.OrdinalIgnoreCase)) return false;
        var batch = source.Query.Contains("batch=1", StringComparison.OrdinalIgnoreCase);
        var isList = source.AbsolutePath.Contains("alertCenter.list", StringComparison.OrdinalIgnoreCase);
        object json = isList ? Array.Empty<object>() : new Dictionary<string, object> { ["ok"] = true };
        var inner = new Dictionary<string, object>
        {
            ["result"] = new Dictionary<string, object>
            {
                ["data"] = new Dictionary<string, object> { ["json"] = json }
            }
        };
        payload = batch ? new object[] { inner } : inner;
        return true;
    }

    private bool TryResolveLocalApi(string rawUri, out Uri target)
    {
        target = new Uri("http://127.0.0.1:8765/");
        if (!Uri.TryCreate(rawUri, UriKind.Absolute, out var source)) return false;
        if (!string.Equals(source.Scheme, "https", StringComparison.OrdinalIgnoreCase) ||
            !string.Equals(source.Host, _config.App.VirtualHost, StringComparison.OrdinalIgnoreCase)) return false;

        var path = source.AbsolutePath;
        if (!path.StartsWith("/api/aura/", StringComparison.OrdinalIgnoreCase)) return false;
        var route = path["/api/aura/".Length..];
        var port = 8765;
        var backendPath = route switch
        {
            "health" => "/api/health",
            "status" => "/api/status",
            "diagnostic" => "/api/diagnostics/deep",
            "agents" => "/api/agents",
            "activation" => "/api/activation",
            "glm" => "/api/agents/glm/status",
            "chat" => "/api/trader/chat",
            "glm-chat" => "/api/glm_chat",
            "ui-state" => "/api/ui/state",
            "feedback" => "/api/feedback",
            "tools" => "/api/tools",
            "bridge" => SwitchBackend("bridge", ref port),
            "voice" => SwitchBackend("voice", ref port),
            "voice-tts" => SwitchBackend("voice-tts", ref port),
            _ when route.StartsWith("agents/", StringComparison.OrdinalIgnoreCase) => SafeAgentRoute(route["agents/".Length..], ref port),
            _ when route.StartsWith("tools/", StringComparison.OrdinalIgnoreCase) => SafeEngineRoute(route, ref port),
            _ => null
        };
        if (backendPath is null) return false;
        var builder = new UriBuilder("http", "127.0.0.1", port, backendPath)
        {
            Query = source.Query.TrimStart('?')
        };
        target = builder.Uri;
        return true;
    }

    private static string? SwitchBackend(string route, ref int port)
    {
        if (route == "bridge") { port = 8080; return "/health"; }
        if (route == "voice") { port = 8099; return "/api/voice/health"; }
        if (route == "voice-tts") { port = 8099; return "/api/voice/tts"; }
        return null;
    }

    private static string? SanitizeApiTail(string route)
    {
        if (string.IsNullOrWhiteSpace(route)) return null;
        string decoded;
        try { decoded = Uri.UnescapeDataString(route); }
        catch (UriFormatException) { return null; }
        decoded = decoded.Replace('\\', '/');
        if (decoded.Contains("..", StringComparison.Ordinal) || decoded.Contains(':', StringComparison.Ordinal))
            return null;
        var parts = decoded.Split('/', StringSplitOptions.RemoveEmptyEntries);
        foreach (var part in parts)
        {
            if (part is "." or "..") return null;
        }
        return string.Join("/", parts);
    }

    private static string? SafeAgentRoute(string route, ref int port)
    {
        var tail = SanitizeApiTail(route);
        if (tail is null) return null;
        port = 8765;
        return "/api/agents/" + tail;
    }

    private static string? SafeEngineRoute(string route, ref int port)
    {
        var tail = SanitizeApiTail(route);
        if (tail is null) return null;
        port = 8765;
        return "/api/" + tail;
    }

    private static string HeaderBlock(params string[] lines)
    {
        return string.Join("\r\n", lines) + "\r\n";
    }

    private async Task<CoreWebView2WebResourceResponse> ForwardLocalApiAsync(CoreWebView2WebResourceRequest request, Uri target)
    {
        var core = _view.CoreWebView2!;
        if (string.Equals(request.Method, "OPTIONS", StringComparison.OrdinalIgnoreCase))
            return CreateJsonResponse(204, "No Content", null);

        using var outgoing = new HttpRequestMessage(new HttpMethod(request.Method), target);
        foreach (var header in request.Headers)
        {
            if (header.Key.Equals("Host", StringComparison.OrdinalIgnoreCase) ||
                header.Key.Equals("Origin", StringComparison.OrdinalIgnoreCase) ||
                header.Key.Equals("Referer", StringComparison.OrdinalIgnoreCase) ||
                header.Key.Equals("Content-Length", StringComparison.OrdinalIgnoreCase)) continue;
            outgoing.Headers.TryAddWithoutValidation(header.Key, header.Value);
        }
        // Alinha token do processo Desktop com o Bridge (captura + latest)
        var bridgeToken = Environment.GetEnvironmentVariable("CORNERAI_BRIDGE_TOKEN");
        if (!string.IsNullOrWhiteSpace(bridgeToken) &&
            !outgoing.Headers.Contains("X-CornerAI-Token"))
        {
            outgoing.Headers.TryAddWithoutValidation("X-CornerAI-Token", bridgeToken.Trim());
        }
        if (request.Content is not null)
        {
            using var buffer = new MemoryStream();
            request.Content.CopyTo(buffer);
            var body = buffer.ToArray();
            outgoing.Content = new ByteArrayContent(body);
            if (request.Headers.GetHeader("Content-Type") is string contentType && !string.IsNullOrWhiteSpace(contentType))
                outgoing.Content.Headers.TryAddWithoutValidation("Content-Type", contentType);
        }

        using var response = await LocalApiClient.SendAsync(outgoing, HttpCompletionOption.ResponseContentRead);
        var bytes = await response.Content.ReadAsByteArrayAsync();
        var contentTypeHeader = response.Content.Headers.ContentType?.ToString() ?? "application/json; charset=utf-8";
        var headers = HeaderBlock(
            "Content-Type: " + contentTypeHeader,
            "Cache-Control: no-store",
            "Access-Control-Allow-Origin: https://" + _config.App.VirtualHost,
            "Access-Control-Allow-Credentials: true",
            "Access-Control-Allow-Headers: Content-Type, X-CornerAI-Token",
            "Access-Control-Allow-Methods: GET, POST, OPTIONS");
        return core.Environment.CreateWebResourceResponse(
            new MemoryStream(bytes), (int)response.StatusCode, response.ReasonPhrase ?? "OK", headers);
    }

    private CoreWebView2WebResourceResponse CreateJsonResponse(int statusCode, string reason, object? payload)
    {
        var bytes = Encoding.UTF8.GetBytes(payload is null ? "" : JsonSerializer.Serialize(payload));
        var headers = HeaderBlock(
            "Content-Type: application/json; charset=utf-8",
            "Access-Control-Allow-Origin: https://" + _config.App.VirtualHost,
            "Access-Control-Allow-Credentials: true",
            "Access-Control-Allow-Headers: Content-Type, X-CornerAI-Token",
            "Access-Control-Allow-Methods: GET, POST, OPTIONS");
        return _view.CoreWebView2!.Environment.CreateWebResourceResponse(
            new MemoryStream(bytes), statusCode, reason, headers);
    }

    public void Navigate(string uri)
    {
        if (_view.CoreWebView2 is null)
        {
            StatusChanged?.Invoke(this, "Navegação ignorada: WebView2 ainda não inicializado.");
            return;
        }
        if (string.IsNullOrWhiteSpace(uri)) return;

        var u = uri.Trim();

        if (!Uri.TryCreate(u, UriKind.Absolute, out var parsed) || !IsAllowedNavigation(parsed))
        {
            StatusChanged?.Invoke(this, $"URL bloqueada: {uri}");
            return;
        }
        if (string.Equals(parsed.Host, _config.App.VirtualHost, StringComparison.OrdinalIgnoreCase) &&
            (string.IsNullOrEmpty(parsed.AbsolutePath) || parsed.AbsolutePath == "/"))
        {
            var builder = new UriBuilder(parsed) { Path = "/index.html" };
            u = builder.Uri.AbsoluteUri;
        }
        _view.CoreWebView2.Navigate(u);
    }

    public void OpenSokkerPro()
    {
        Navigate("https://sokkerpro.com/");
    }

    public void Back() { if (_view.CoreWebView2?.CanGoBack == true) _view.CoreWebView2.GoBack(); }
    public void Forward() { if (_view.CoreWebView2?.CanGoForward == true) _view.CoreWebView2.GoForward(); }
    public void Reload() { if (_view.CoreWebView2 is not null) _view.CoreWebView2.Reload(); }

    private static readonly HashSet<int> LoopbackPorts = new()
    {
        80, 443, 8080, 8099, 8765, 8766, 8777, 8790
    };

    private bool IsAllowedHost(string host)
    {
        host = host.Trim().TrimEnd('.').ToLowerInvariant();
        foreach (var configured in _config.Browser.AllowedHosts)
        {
            var item = configured.Trim().TrimEnd('.').ToLowerInvariant();
            if (host == item) return true;
        }
        return host == _config.App.VirtualHost.ToLowerInvariant();
    }

    private bool IsAllowedNavigation(Uri uri)
    {
        if (!IsAllowedHost(uri.Host)) return false;
        var host = uri.Host.Trim().TrimEnd('.').ToLowerInvariant();
        if (host is not ("127.0.0.1" or "localhost")) return true;
        var port = uri.IsDefaultPort ? (string.Equals(uri.Scheme, "https", StringComparison.OrdinalIgnoreCase) ? 443 : 80) : uri.Port;
        return LoopbackPorts.Contains(port);
    }

    private void OnWebMessageReceived(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        try
        {
            using var doc = JsonDocument.Parse(e.WebMessageAsJson);
            if (!doc.RootElement.TryGetProperty("type", out var type)) return;
            var messageType = type.GetString() ?? "";
            if (messageType == "AURA_SOKKERPRO_CAPTURE" &&
                doc.RootElement.TryGetProperty("payload", out var payload))
            {
                var source = e.Source ?? "";
                if (Uri.TryCreate(source, UriKind.Absolute, out var uri) && IsSokkerHost(uri.Host))
                {
                    Interlocked.Increment(ref _capturesEmitted);
                    CaptureReceived?.Invoke(this, payload.GetRawText());
                }
                return;
            }
            if (messageType == "CAPTURE_ERROR")
            {
                var detail = doc.RootElement.TryGetProperty("detail", out var detailNode)
                    ? detailNode.GetString() ?? "DOM_BROKEN_OR_PAGE_UNLOADED"
                    : "DOM_BROKEN_OR_PAGE_UNLOADED";
                StatusChanged?.Invoke(this, "DOM Canary: " + detail);
                return;
            }
            if (messageType == "AURA_OPEN_SOKKERPRO")
                OpenSokkerPro();
        }
        catch (JsonException ex)
        {
            StatusChanged?.Invoke(this, $"Mensagem WebView2 inválida: {ex.Message}");
        }
    }

    private static readonly HashSet<string> AllowedSokkerHosts = new(StringComparer.OrdinalIgnoreCase)
    {
        "sokkerpro.com", "www.sokkerpro.com", "m2.sokkerpro.com", "m3.sokkerpro.com", "m4.sokkerpro.com", "app.sokkerpro.com"
    };

    private bool IsSokkerHost(string host)
    {
        return AllowedSokkerHosts.Contains(host.Trim().TrimEnd('.'));
    }

    private async void InjectAuraCaptureAsync()
    {
        try
        {
            if (!IsSokkerHost(_view.Source?.Host ?? "")) return;
            if (string.IsNullOrWhiteSpace(_captureScript))
            {
                var path = Path.Combine(AppContext.BaseDirectory, "capture", "aura-capture.js");
                if (!File.Exists(path)) return;
                _captureScript = await File.ReadAllTextAsync(path);
            }
            if (_view.CoreWebView2 is not null && !string.IsNullOrWhiteSpace(_captureScript))
                await _view.CoreWebView2.ExecuteScriptAsync(_captureScript);
        }
        catch (Exception ex)
        {
            StatusChanged?.Invoke(this, $"Falha ao injetar script de captura: {ex.Message}");
        }
    }
}

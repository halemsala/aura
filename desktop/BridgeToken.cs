using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;

namespace Aura.QuantX.Desktop;

/// <summary>
/// Garante e carrega CORNERAI_BRIDGE_TOKEN no processo atual (DPAPI CurrentUser).
/// Compatível com scripts/prepare_bridge_token.ps1 (mesmo path e mesmo scope).
/// Sem este token o CaptureForwarder descarta capturas em silêncio e o Bridge
/// responde 401/503 em /api/cornerai/feed — Matriz cai em FALLBACK DEMONSTRATIVO.
/// </summary>
internal static class BridgeToken
{
    private static readonly string DefaultPath = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "AURA_QUANT_X", "secure", "cornerai_bridge_token.bin");

    public static string TokenPath => DefaultPath;

    /// <summary>
    /// Garante ficheiro, carrega token e define variáveis de ambiente no processo.
    /// Retorna o token (nunca null se ok); lança em falha crítica.
    /// </summary>
    public static string EnsureAndApply(Action<string>? log = null)
    {
        var existing = Environment.GetEnvironmentVariable("CORNERAI_BRIDGE_TOKEN");
        if (!string.IsNullOrWhiteSpace(existing))
        {
            log?.Invoke("BRIDGE_TOKEN: já presente no ambiente (não regenerado).");
            // Nao forcar REQUIRE=1 se o operador pediu Bridge aberto local
            var req = Environment.GetEnvironmentVariable("CORNERAI_BRIDGE_REQUIRE_TOKEN");
            if (string.IsNullOrWhiteSpace(req))
                Environment.SetEnvironmentVariable("CORNERAI_BRIDGE_REQUIRE_TOKEN", "1");
            return existing.Trim();
        }

        // Tenta script oficial se existir (mesma lógica do BAT)
        var rootCandidates = new[]
        {
            AppContext.BaseDirectory,
            Directory.GetCurrentDirectory(),
        };
        foreach (var root in rootCandidates)
        {
            var script = Path.Combine(root, "scripts", "prepare_bridge_token.ps1");
            if (!File.Exists(script))
            {
                // sobe até 6 níveis à procura da raiz do pacote
                var dir = new DirectoryInfo(root);
                for (var i = 0; i < 6 && dir is not null; i++, dir = dir.Parent)
                {
                    var candidate = Path.Combine(dir.FullName, "scripts", "prepare_bridge_token.ps1");
                    if (File.Exists(candidate))
                    {
                        script = candidate;
                        break;
                    }
                }
            }
            if (File.Exists(script))
            {
                try
                {
                    RunPsEnsure(script, DefaultPath, log);
                    var loaded = RunPsLoad(script, DefaultPath, log);
                    if (!string.IsNullOrWhiteSpace(loaded))
                    {
                        ApplyEnv(loaded);
                        log?.Invoke("BRIDGE_TOKEN: provisionado via prepare_bridge_token.ps1.");
                        return loaded;
                    }
                }
                catch (Exception ex)
                {
                    log?.Invoke("BRIDGE_TOKEN: script falhou, fallback DPAPI nativo: " + ex.Message);
                }
                break;
            }
        }

        // Fallback nativo DPAPI (mesmo path/scope do script)
        var token = EnsureNative(DefaultPath, log);
        ApplyEnv(token);
        log?.Invoke("BRIDGE_TOKEN: provisionado via DPAPI nativo.");
        return token;
    }

    private static void ApplyEnv(string token)
    {
        Environment.SetEnvironmentVariable("CORNERAI_BRIDGE_TOKEN", token);
        var req = Environment.GetEnvironmentVariable("CORNERAI_BRIDGE_REQUIRE_TOKEN");
        if (string.IsNullOrWhiteSpace(req))
            Environment.SetEnvironmentVariable("CORNERAI_BRIDGE_REQUIRE_TOKEN", "1");
    }

    private static string EnsureNative(string path, Action<string>? log)
    {
        var dir = Path.GetDirectoryName(path);
        if (!string.IsNullOrWhiteSpace(dir))
            Directory.CreateDirectory(dir);

        if (File.Exists(path))
        {
            var cipher = File.ReadAllBytes(path);
            if (cipher.Length >= 32)
            {
                var plain = ProtectedData.Unprotect(cipher, null, DataProtectionScope.CurrentUser);
                var asText = Encoding.UTF8.GetString(plain);
                if (asText.IndexOf('\0') >= 0)
                    return Convert.ToHexString(plain).ToLowerInvariant();
                return asText;
            }
            log?.Invoke("BRIDGE_TOKEN: ficheiro inválido; a regenerar.");
        }

        var hex = Convert.ToHexString(RandomNumberGenerator.GetBytes(32)).ToLowerInvariant();
        var raw = Encoding.UTF8.GetBytes(hex);
        var protectedBytes = ProtectedData.Protect(raw, null, DataProtectionScope.CurrentUser);
        var tmp = path + "." + Environment.ProcessId + ".tmp";
        File.WriteAllBytes(tmp, protectedBytes);
        File.Move(tmp, path, overwrite: true);
        return hex;
    }

    private static void RunPsEnsure(string script, string path, Action<string>? log)
    {
        var psi = new ProcessStartInfo
        {
            FileName = "powershell.exe",
            Arguments = $"-NoProfile -ExecutionPolicy Bypass -File \"{script}\" -Mode Ensure -Path \"{path}\"",
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
        };
        using var p = Process.Start(psi) ?? throw new InvalidOperationException("powershell não iniciou");
        var err = p.StandardError.ReadToEnd();
        p.WaitForExit(15000);
        if (p.ExitCode != 0)
            throw new InvalidOperationException("Ensure token exit=" + p.ExitCode + " " + err);
    }

    private static string RunPsLoad(string script, string path, Action<string>? log)
    {
        var psi = new ProcessStartInfo
        {
            FileName = "powershell.exe",
            Arguments = $"-NoProfile -ExecutionPolicy Bypass -File \"{script}\" -Mode Load -Path \"{path}\"",
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
        };
        using var p = Process.Start(psi) ?? throw new InvalidOperationException("powershell não iniciou");
        var output = p.StandardOutput.ReadToEnd();
        var err = p.StandardError.ReadToEnd();
        p.WaitForExit(15000);
        if (p.ExitCode != 0)
            throw new InvalidOperationException("Load token exit=" + p.ExitCode + " " + err);
        return (output ?? "").Trim();
    }
}

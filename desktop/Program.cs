using System.Text;
using System.Text.Json;

namespace Aura.QuantX.Desktop;

internal static class Program
{
    private static readonly string ProcessLogPath = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "AURA_QUANT_X", "logs", "desktop_process.log");

    [STAThread]
    private static void Main()
    {
        try
        {
            Application.ThreadException += (_, args) => Log("THREAD_EXCEPTION: " + args.Exception);
            AppDomain.CurrentDomain.UnhandledException += (_, args) => Log("UNHANDLED_EXCEPTION: " + args.ExceptionObject);
            Log($"START pid={Environment.ProcessId} base={AppContext.BaseDirectory} cwd={Environment.CurrentDirectory}");

            using var singleInstance = new Mutex(true, "AURA_QUANTX_V25_DESKTOP_MUTEX", out var createdNew);
            if (!createdNew)
            {
                Log("MUTEX_COLLISION: outra instância informou o mutex AURA_QUANTX_V25_DESKTOP_MUTEX.");
                MessageBox.Show("O AURA QUANT-X Desktop já está aberto.", "AURA QUANT-X", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }

            ApplicationConfiguration.Initialize();
            var root = FindRoot();
            var configPath = Path.Combine(root, "desktop", "config", "desktop.json");
            Log($"ROOT={root} config={configPath} config_exists={File.Exists(configPath)}");

            // V25T6-FIX: token obrigatório para CaptureForwarder → Bridge.
            // Sem isto a captura do SokkerPRO é descartada em silêncio e a Matriz
            // cai em FALLBACK DEMONSTRATIVO ("modo simulado").
            try
            {
                var token = BridgeToken.EnsureAndApply(Log);
                Log($"BRIDGE_TOKEN: ok len={token.Length} path={BridgeToken.TokenPath}");
            }
            catch (Exception tex)
            {
                Log("BRIDGE_TOKEN_FATAL: " + tex);
                MessageBox.Show(
                    "Não foi possível provisionar CORNERAI_BRIDGE_TOKEN.\n\n" +
                    tex.Message + $"\n\nPath: {BridgeToken.TokenPath}\nLog: {ProcessLogPath}",
                    "AURA Desktop — token Bridge",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                Environment.ExitCode = 2;
                return;
            }

            var config = LoadConfig(configPath);
            config.Security.AllowRealOrders = false;
            config.App.PaperTradeOnly = true;

            using var form = new MainForm(root, config);
            form.FormClosed += (_, _) => Log("FORM_CLOSED: janela principal fechada.");
            Application.Run(form);
            Log("APPLICATION_RUN_RETURNED: loop WinForms terminou normalmente.");
        }
        catch (Exception ex)
        {
            Log("FATAL_BOOTSTRAP_EXCEPTION: " + ex);
            try
            {
                MessageBox.Show(
                    ex.Message + $"\n\nLog: {ProcessLogPath}",
                    "AURA Desktop",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
            catch
            {
                // O log persistente é a fonte de diagnóstico quando a UI não puder abrir.
            }
            Environment.ExitCode = 1;
        }
    }

    private static void Log(string line)
    {
        try
        {
            var directory = Path.GetDirectoryName(ProcessLogPath);
            if (!string.IsNullOrWhiteSpace(directory)) Directory.CreateDirectory(directory);
            File.AppendAllText(
                ProcessLogPath,
                $"[{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss zzz}] {line}{Environment.NewLine}",
                Encoding.UTF8);
        }
        catch
        {
            // Diagnóstico nunca pode impedir o bootstrap do Desktop.
        }
    }

    private static string FindRoot()
    {
        // Sobe a arvore de diretorios ate achar desktop/config/desktop.json
        // (funciona tanto em dev quanto em publish single-file / bin/Debug)
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        for (var i = 0; i < 8 && dir is not null; i++, dir = dir.Parent)
        {
            var marker = Path.Combine(dir.FullName, "desktop", "config", "desktop.json");
            if (File.Exists(marker))
                return Path.GetFullPath(dir.FullName);
        }
        // Fallback: tenta tambem o cwd (quando rodado da raiz do projeto)
        var cwd = Directory.GetCurrentDirectory();
        if (File.Exists(Path.Combine(cwd, "desktop", "config", "desktop.json")))
            return Path.GetFullPath(cwd);
        return Path.GetFullPath(AppContext.BaseDirectory);
    }

    private static DesktopConfig LoadConfig(string path)
    {
        if (!File.Exists(path))
            return new DesktopConfig();
        try
        {
            var options = new JsonSerializerOptions { PropertyNameCaseInsensitive = true };
            return JsonSerializer.Deserialize<DesktopConfig>(File.ReadAllText(path), options) ?? new DesktopConfig();
        }
        catch (Exception ex)
        {
            Log("CONFIG_LOAD_EXCEPTION: " + ex);
            return new DesktopConfig();
        }
    }
}

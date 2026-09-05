using Microsoft.Web.WebView2.Core;

namespace Aura.QuantX.Desktop;

/// <summary>
/// Ambiente WebView2 COMPARTILHADO por todos os controles do AURA
/// (dashboard + browser de captura). Um unico processo de browser para o app
/// inteiro = a maior economia de memoria disponivel, alem de teto de cache
/// de disco bornado (fixture JSON e leve; cache maior nao acelera nada).
/// Nota: os flags de cache valem a partir do START do processo browser —
/// mudar DiskCacheMb exige restart do app.
/// </summary>
public static class WebViewEnvironmentFactory
{
    private static readonly SemaphoreSlim _gate = new(1, 1);
    private static CoreWebView2Environment? _shared;
    private static string _sharedFolder = "";

    public static async Task<CoreWebView2Environment> GetSharedAsync(
        string userDataFolder, int diskCacheMb = 256)
    {
        if (string.IsNullOrWhiteSpace(userDataFolder))
            throw new ArgumentException("userDataFolder obrigatorio", nameof(userDataFolder));

        await _gate.WaitAsync();
        try
        {
            if (_shared is not null &&
                string.Equals(_sharedFolder, userDataFolder, StringComparison.OrdinalIgnoreCase))
                return _shared;

            var bytes = Math.Max(8, diskCacheMb) * 1024 * 1024;
            var options = new CoreWebView2EnvironmentOptions
            {
                AdditionalBrowserArguments =
                    "--disk-cache-size=" + bytes +
                    " --media-cache-size=" + (bytes / 2) +
                    " --autoplay-policy=user-gesture-required"
            };
            _shared = await CoreWebView2Environment.CreateAsync(null, userDataFolder, options);
            _sharedFolder = userDataFolder;
            return _shared;
        }
        finally { _gate.Release(); }
    }
}

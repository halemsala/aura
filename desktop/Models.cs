using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Aura.QuantX.Desktop;

public sealed class DesktopConfig
{
    public AppConfig App { get; set; } = new();
    public BrowserConfig Browser { get; set; } = new();
    public List<ServiceConfig> Services { get; set; } = new();
    public OllamaConfig Ollama { get; set; } = new();
    public SecurityConfig Security { get; set; } = new();
    public AdminConfig Admin { get; set; } = new();
}

public sealed class AppConfig
{
    public string DisplayName { get; set; } = "AURA QUANT-X Desktop";
    public string Version { get; set; } = "12.7.62-V25Q-OPERATOR-OS-FINAL";
    public string VirtualHost { get; set; } = "aura.local";
    public string Homepage { get; set; } = "https://aura.local/index.html";
    public string UserDataFolder { get; set; } = "desktop_data";
    public bool PaperTradeOnly { get; set; } = true;
    public List<string> FallbackHomepages { get; set; } = new()
    {
        "https://aura.local/index.html"
    };
}

public sealed class BrowserConfig
{
    public string Engine { get; set; } = "WebView2";
    public bool ChromiumCompatible { get; set; } = true;
    public bool OperaBinary { get; set; }
    public List<string> AllowedHosts { get; set; } = new();
    public string CaptureScript { get; set; } = "desktop/capture/aura-capture.js";
}

public sealed class ServiceConfig
{
    public string Name { get; set; } = "";
    public string WorkingDirectory { get; set; } = ".";
    public string Python { get; set; } = "engine/venv/Scripts/python.exe";
    public string Script { get; set; } = "";
    public List<string> Arguments { get; set; } = new();
    public int Port { get; set; }
    public string HealthUrl { get; set; } = "";
    public bool Enabled { get; set; } = true;
}

public sealed class OllamaConfig
{
    public List<string> ExecutableCandidates { get; set; } = new();
    public string BaseUrl { get; set; } = "http://127.0.0.1:11434";
    public string Model { get; set; } = "llama3.2:3b";
    public string FallbackModel { get; set; } = "llama3.2:3b";
}

public sealed class SecurityConfig
{
    public List<string> BridgeAllowedOrigins { get; set; } = new();
    public bool AllowRealOrders { get; set; }
    public bool RequireAdminForRestrictedActions { get; set; } = true;
}

public sealed class AdminConfig
{
    public string ApiBaseUrl { get; set; } = "http://127.0.0.1:8765";
    public string DefaultMode { get; set; } = "PLAN_ONLY";
    public bool RequireExplicitApproval { get; set; } = true;
    public bool PaperTradeOnly { get; set; } = true;
    public string CheckpointPath { get; set; } = "runtime/checkpoints";
}

public sealed record ServiceStatus(string Name, int Port, string HealthUrl, bool Healthy, string Detail);

public sealed class CaptureEnvelope
{
    [JsonPropertyName("type")]
    public string Type { get; set; } = "AURA_SOKKERPRO_CAPTURE";

    [JsonPropertyName("payload")]
    public Dictionary<string, object?> Payload { get; set; } = new();
}

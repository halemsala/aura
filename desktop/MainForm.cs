using System.Drawing;
using System.Windows.Forms;
using Microsoft.Web.WebView2.WinForms;

namespace Aura.QuantX.Desktop;

/// <summary>
/// Single-surface Operator OS: custom chrome (min/max/close) + Matriz + SokkerPRO navigation.
/// </summary>
public sealed class MainForm : Form
{
    private readonly string _root;
    private readonly DesktopConfig _config;
    private readonly ServiceSupervisor _supervisor;
    private readonly Panel _titleBar = new();
    private readonly Label _titleLabel = new();
    private readonly Button _btnMatriz = new();
    private readonly Button _btnSokker = new();
    private readonly Button _btnMin = new();
    private readonly Button _btnMax = new();
    private readonly Button _btnClose = new();
    private readonly WebView2 _webView = new();
    private BrowserHost? _browser;
    private readonly CaptureForwarder _forwarder = new(2000);
    private readonly CancellationTokenSource _monitorCts = new();
    private Point _dragStart;
    private bool _dragging;
    private DateTime _lastF11 = DateTime.MinValue;
    private static readonly TimeSpan F11Debounce = TimeSpan.FromMilliseconds(400);

    public MainForm(string root, DesktopConfig config)
    {
        _root = Path.GetFullPath(root);
        _config = config;
        _supervisor = new ServiceSupervisor(_root, _config);
        _forwarder.IngestUrl = "http://127.0.0.1:8080/api/cornerai/feed";

        Text = $"{_config.App.DisplayName} · OPERATOR OS";
        WindowState = FormWindowState.Maximized;
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.FromArgb(16, 20, 28);
        MinimumSize = new Size(1024, 640);
        KeyPreview = true;
        KeyDown += OnKeyDown;

        BuildTitleBar();
        _webView.Dock = DockStyle.Fill;

        Controls.Add(_webView);
        Controls.Add(_titleBar);

        Load += OnLoadedAsync;
        FormClosing += (_, _) =>
        {
            try { _monitorCts.Cancel(); } catch { }
            _forwarder.Dispose();
            _supervisor.DisposeAsync().AsTask().GetAwaiter().GetResult();
            try { _monitorCts.Dispose(); } catch { }
        };
    }

    private void BuildTitleBar()
    {
        _titleBar.Dock = DockStyle.Top;
        _titleBar.Height = 40;
        _titleBar.BackColor = Color.FromArgb(22, 28, 36);
        _titleBar.Padding = new Padding(8, 0, 4, 0);

        _titleLabel.Text = "AURA Operator OS  |  F2 SokkerPRO  |  F1 Matriz  |  F11 Max";
        _titleLabel.ForeColor = Color.FromArgb(180, 220, 190);
        _titleLabel.Font = new Font("Segoe UI", 9f, FontStyle.Regular);
        _titleLabel.AutoSize = false;
        _titleLabel.Dock = DockStyle.Fill;
        _titleLabel.TextAlign = ContentAlignment.MiddleLeft;
        _titleLabel.MouseDown += TitleBarMouseDown;
        _titleLabel.MouseMove += TitleBarMouseMove;
        _titleLabel.MouseUp += (_, _) => _dragging = false;

        StyleChromeButton(_btnMatriz, "Matriz", Color.FromArgb(40, 80, 60));
        StyleChromeButton(_btnSokker, "SokkerPRO", Color.FromArgb(50, 70, 100));
        StyleChromeButton(_btnMin, "_", Color.FromArgb(40, 45, 55));
        StyleChromeButton(_btnMax, "[]", Color.FromArgb(40, 45, 55));
        StyleChromeButton(_btnClose, "X", Color.FromArgb(90, 40, 40));

        _btnMatriz.Click += (_, _) => GoMatriz();
        _btnSokker.Click += (_, _) => GoSokkerPro();
        _btnMin.Click += (_, _) => WindowState = FormWindowState.Minimized;
        _btnMax.Click += (_, _) => ToggleMax();
        _btnClose.Click += (_, _) => Close();

        var right = new FlowLayoutPanel
        {
            Dock = DockStyle.Right,
            FlowDirection = FlowDirection.LeftToRight,
            WrapContents = false,
            AutoSize = true,
            BackColor = Color.FromArgb(22, 28, 36),
            Padding = new Padding(0, 4, 0, 4),
        };
        foreach (var b in new[] { _btnMatriz, _btnSokker, _btnMin, _btnMax, _btnClose })
        {
            b.Width = b == _btnSokker || b == _btnMatriz ? 88 : 40;
            b.Height = 30;
            b.Margin = new Padding(3, 0, 0, 0);
            right.Controls.Add(b);
        }

        _titleBar.Controls.Add(_titleLabel);
        _titleBar.Controls.Add(right);
    }

    private static void StyleChromeButton(Button b, string text, Color back)
    {
        b.Text = text;
        b.FlatStyle = FlatStyle.Flat;
        b.FlatAppearance.BorderSize = 0;
        b.BackColor = back;
        b.ForeColor = Color.FromArgb(220, 230, 230);
        b.Font = new Font("Segoe UI", 8.5f, FontStyle.Bold);
        b.Cursor = Cursors.Hand;
    }

    private void TitleBarMouseDown(object? sender, MouseEventArgs e)
    {
        if (e.Button != MouseButtons.Left) return;
        _dragging = true;
        _dragStart = e.Location;
        if (WindowState == FormWindowState.Maximized)
        {
            WindowState = FormWindowState.Normal;
            Location = new Point(Cursor.Position.X - Width / 2, Cursor.Position.Y - 20);
        }
    }

    private void TitleBarMouseMove(object? sender, MouseEventArgs e)
    {
        if (!_dragging || e.Button != MouseButtons.Left) return;
        Location = new Point(Location.X + e.X - _dragStart.X, Location.Y + e.Y - _dragStart.Y);
    }

    private void ToggleMax()
    {
        WindowState = WindowState == FormWindowState.Maximized
            ? FormWindowState.Normal
            : FormWindowState.Maximized;
    }

    private void OnKeyDown(object? sender, KeyEventArgs e)
    {
        if (e.KeyCode == Keys.F11)
        {
            var now = DateTime.UtcNow;
            if (now - _lastF11 < F11Debounce)
            {
                e.Handled = true;
                e.SuppressKeyPress = true;
                return;
            }
            _lastF11 = now;
            ToggleMax();
            e.Handled = true;
            e.SuppressKeyPress = true;
            return;
        }
        if (e.KeyCode == Keys.F1) { GoMatriz(); e.Handled = true; e.SuppressKeyPress = true; }
        else if (e.KeyCode == Keys.F2) { GoSokkerPro(); e.Handled = true; e.SuppressKeyPress = true; }
        else if (e.KeyCode == Keys.Escape && WindowState == FormWindowState.Maximized)
        { WindowState = FormWindowState.Normal; e.Handled = true; e.SuppressKeyPress = true; }
    }

    private void GoMatriz()
    {
        try
        {
            var home = string.IsNullOrWhiteSpace(_config.App.Homepage)
                ? "https://aura.local/index.html"
                : _config.App.Homepage;
            _browser?.Navigate(home);
            _titleLabel.Text = "AURA Operator OS  |  Matriz V25Q  |  F2 SokkerPRO";
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, ex.Message, "Matriz", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
    }

    private void GoSokkerPro()
    {
        try
        {
            if (_browser is null)
            {
                MessageBox.Show(this, "WebView ainda inicializando.", "SokkerPRO", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            _browser.OpenSokkerPro();
            _titleLabel.Text = "AURA  |  SokkerPRO (captura ativa)  |  F1 voltar Matriz";
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, ex.Message, "SokkerPRO", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
    }

    private void OnCaptureReceived(object? sender, string payload)
    {
        _forwarder.Enqueue(payload);
    }

    private async void OnLoadedAsync(object? sender, EventArgs e)
    {
        try
        {
            var statuses = await _supervisor.StartAllAsync();
            _ = Task.Run(() => _supervisor.MonitorServicesAsync(_monitorCts.Token));
            await _supervisor.CheckOllamaAsync();

            _browser = new BrowserHost(_webView, _root, _config);
            _browser.CaptureReceived += OnCaptureReceived;
            await _browser.InitializeAsync(operatorShell: true);
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                this,
                ex.Message + $"\n\nLog: {_supervisor.LogPath}",
                "AURA Operator OS",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
    }
}

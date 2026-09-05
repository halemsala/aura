// ============================================================================
// CaptureForwarder.cs — encaminha capturas do WebView2 (C#) para o engine (Python).
//
// Disciplina do feed_bus aplicada em C#:
// - fila LIMITADA com drop-OLDEST contabilizado (analise live quer o fresco);
// - retry limitado (6 tentativas) com backoff Equal Jitter via BackoffPolicy;
// - IngestUrl vazio = encaminhador DESLIGADO (descarta contabilizado, nao
// acumula memoria);
// - Stats() com todos os contadores; nenhum drop e silencioso.
// Nao toca em caminho de aposta (§0): move JSON de captura, nada mais.
//
// Validacao isolada (PowerShell):
// Add-Type -Path "desktop\BackoffPolicy.cs"
// Add-Type -Path "desktop\CaptureForwarder.cs"
// [Aura.QuantX.Desktop.CaptureForwarder]::RunSelfTest()
// ============================================================================
using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Aura.QuantX.Desktop
{
    public sealed class CaptureForwarder : IDisposable
    {
        private const int MaxAttemptsPerItem = 6;
        private readonly object _gate = new object();
        private readonly Queue<string> _pending = new Queue<string>();
        private readonly int _maxQueue;
        private readonly Func<string, Task<bool>> _send;
        private readonly BackoffPolicy _backoff;
        private readonly SemaphoreSlim _signal = new SemaphoreSlim(0);
        private readonly CancellationTokenSource _cts = new CancellationTokenSource();
        private readonly HttpClient _http = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
        private Task? _loop;
        private long _enqueued, _delivered, _droppedOverflow, _droppedDisabled,
                    _droppedFailed, _retries;
        private int _missingTokenLogged;

        /// <summary>Endpoint de ingest do engine (ex.: http://127.0.0.1:8080/api/cornerai/feed).
        /// Vazio = encaminhador desligado (capturas contadas como descartadas).</summary>
        public string? IngestUrl { get; set; }

        public CaptureForwarder(int maxQueue = 2000)
            : this(null, maxQueue,
                   new BackoffPolicy(500, 10000, BackoffJitterMode.Equal, null, 30000), true)
        {
        }

        internal CaptureForwarder(Func<string, Task<bool>>? send, int maxQueue,
                                  BackoffPolicy backoff, bool autoStart)
        {
            _maxQueue = maxQueue <= 0 ? 1 : maxQueue;
            _backoff = backoff;
            _send = send ?? SendViaHttpAsync;
            if (autoStart)
                _loop = Task.Run((Func<Task>)DrainAsync);
        }

        public void Start()
        {
            lock (_gate)
            {
                if (_loop == null)
                    _loop = Task.Run((Func<Task>)DrainAsync);
            }
        }

        /// <summary>Nunca bloqueia a UI thread; nunca lança.</summary>
        public void Enqueue(string payload)
        {
            if (string.IsNullOrEmpty(payload)) return;
            lock (_gate)
            {
                if (string.IsNullOrEmpty(IngestUrl))
                {
                    Interlocked.Increment(ref _droppedDisabled);
                    return;
                }
                while (_pending.Count >= _maxQueue)
                {
                    _pending.Dequeue(); // drop MAIS ANTIGO
                    Interlocked.Increment(ref _droppedOverflow);
                }
                _pending.Enqueue(payload);
                Interlocked.Increment(ref _enqueued);
            }
            _signal.Release();
        }

        private async Task DrainAsync()
        {
            var token = _cts.Token;
            while (!token.IsCancellationRequested)
            {
                try { await _signal.WaitAsync(token); }
                catch (OperationCanceledException) { break; }

                string? item = null;
                lock (_gate)
                {
                    if (_pending.Count > 0) item = _pending.Dequeue();
                }
                if (item == null) continue;

                bool ok = false;
                for (int attempt = 0;
                     attempt < MaxAttemptsPerItem && !token.IsCancellationRequested;
                     attempt++)
                {
                    try { ok = await _send(item); }
                    catch (Exception) { ok = false; }
                    if (ok) break;
                    Interlocked.Increment(ref _retries);
                    int delayMs = (int)Math.Min(_backoff.NextDelayMs(), int.MaxValue);
                    try { await Task.Delay(delayMs, token); }
                    catch (OperationCanceledException) { break; }
                }
                if (ok)
                {
                    Interlocked.Increment(ref _delivered);
                    _backoff.NotifyHealthy();
                }
                else
                {
                    Interlocked.Increment(ref _droppedFailed);
                }
            }
        }

        private async Task<bool> SendViaHttpAsync(string payload)
        {
            var url = IngestUrl;
            if (string.IsNullOrEmpty(url)) return false;
            var token = Environment.GetEnvironmentVariable("CORNERAI_BRIDGE_TOKEN");
            if (string.IsNullOrWhiteSpace(token))
            {
                // Antes: falha silenciosa → Matriz em FALLBACK DEMONSTRATIVO.
                Interlocked.Increment(ref _droppedFailed);
                if (Interlocked.CompareExchange(ref _missingTokenLogged, 1, 0) == 0)
                {
                    try
                    {
                        var logDir = Path.Combine(
                            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                            "AURA_QUANT_X", "logs");
                        Directory.CreateDirectory(logDir);
                        File.AppendAllText(
                            Path.Combine(logDir, "capture_forwarder.log"),
                            $"[{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss}] CORNERAI_BRIDGE_TOKEN vazio — captura descartada.\n");
                    }
                    catch { /* diagnóstico nunca bloqueia */ }
                }
                return false;
            }
            try
            {
                using (var request = new HttpRequestMessage(HttpMethod.Post, url))
                using (var content = new StringContent(payload, Encoding.UTF8, "application/json"))
                {
                    request.Content = content;
                    request.Headers.TryAddWithoutValidation("X-CornerAI-Token", token);
                    using (var resp = await _http.SendAsync(request))
                    {
                        return resp.IsSuccessStatusCode;
                    }
                }
            }
            catch (Exception)
            {
                return false;
            }
        }

        public Dictionary<string, object> Stats()
        {
            lock (_gate)
            {
                return new Dictionary<string, object>
                {
                    { "enqueued", Interlocked.Read(ref _enqueued) },
                    { "delivered", Interlocked.Read(ref _delivered) },
                    { "pending", _pending.Count },
                    { "dropped_overflow", Interlocked.Read(ref _droppedOverflow) },
                    { "dropped_disabled", Interlocked.Read(ref _droppedDisabled) },
                    { "dropped_failed", Interlocked.Read(ref _droppedFailed) },
                    { "retries", Interlocked.Read(ref _retries) },
                    { "max_queue", _maxQueue },
                    { "ingest_url_configured", !string.IsNullOrEmpty(IngestUrl) }
                };
            }
        }

        public void Dispose()
        {
            _cts.Cancel();
            try { _signal.Release(); } catch (SemaphoreFullException) { }
            try { if (_loop != null) _loop.Wait(TimeSpan.FromSeconds(3)); } catch { }
            _http.Dispose();
            _cts.Dispose();
            _signal.Dispose();
        }

        public static bool RunSelfTest()
        {
            int pass = 0, fail = 0;
            Action<string, bool> check = (name, cond) =>
            {
                Console.WriteLine("[{0}] {1}", cond ? "PASS" : "FAIL", name);
                if (cond) pass++; else fail++;
            };
            Func<Func<bool>, bool> waitFor = cond =>
            {
                for (int i = 0; i < 200; i++)
                {
                    if (cond()) return true;
                    Thread.Sleep(50);
                }
                return false;
            };

            var sent = new List<string>();
            object sentGate = new object();
            var f1 = new CaptureForwarder(p =>
            {
                lock (sentGate) sent.Add(p);
                return Task.FromResult(true);
            }, 100, new BackoffPolicy(10, 20, BackoffJitterMode.Equal, 7, 1000), true);
            f1.IngestUrl = "test://local";
            f1.Enqueue("p1"); f1.Enqueue("p2"); f1.Enqueue("p3");
            check("entrega basica 3/3", waitFor(() =>
            {
                var s = f1.Stats();
                return (long)s["delivered"] == 3 && (int)s["pending"] == 0;
            }));
            lock (sentGate) check("conteudo entregue na ordem",
                sent.Count == 3 && sent[0] == "p1" && sent[2] == "p3");
            f1.Dispose();

            int calls = 0;
            var f2 = new CaptureForwarder(p =>
            {
                int c = Interlocked.Increment(ref calls);
                return Task.FromResult(c > 2);
            }, 10, new BackoffPolicy(5, 10, BackoffJitterMode.Equal, 3, 1000), true);
            f2.IngestUrl = "test://local";
            f2.Enqueue("x");
            check("retry entrega apos falhas", waitFor(() => (long)f2.Stats()["delivered"] == 1));
            check("retries contadas (=2)", (long)f2.Stats()["retries"] == 2);
            f2.Dispose();

            var f3 = new CaptureForwarder(p => Task.FromResult(false), 10,
                new BackoffPolicy(1, 5, BackoffJitterMode.Equal, 11, 1000), true);
            f3.IngestUrl = "test://local";
            f3.Enqueue("y");
            check("falha persistente -> drop contabilizado",
                waitFor(() => (long)f3.Stats()["dropped_failed"] == 1));
            f3.Dispose();

            var f4 = new CaptureForwarder(p => Task.FromResult(true), 2,
                new BackoffPolicy(1, 5, BackoffJitterMode.Equal, 13, 1000), false);
            f4.IngestUrl = "test://local";
            f4.Enqueue("a"); f4.Enqueue("b"); f4.Enqueue("c"); f4.Enqueue("d"); f4.Enqueue("e");
            var s4 = f4.Stats();
            check("overflow: pendentes limitados ao teto", (int)s4["pending"] == 2);
            check("overflow: 3 drops contabilizados", (long)s4["dropped_overflow"] == 3);
            f4.Dispose();

            var f5 = new CaptureForwarder(p => Task.FromResult(true), 10,
                new BackoffPolicy(1, 5, BackoffJitterMode.Equal, 17, 1000), false);
            f5.Enqueue("z"); f5.Enqueue("z2");
            var s5 = f5.Stats();
            check("ingest desligado: descarta e conta",
                (long)s5["dropped_disabled"] == 2 && (int)s5["pending"] == 0);
            f5.Dispose();

            Console.WriteLine(fail == 0
                ? "ALL TESTS PASSED - CaptureForwarder.cs"
                : "SELF-TEST FALHOU: " + fail);
            return fail == 0;
        }
    }
}

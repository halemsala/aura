// ============================================================================
// BackoffPolicy.cs — backoff exponencial com jitter para reinicio de servicos.
// MODULO ADITIVO: nao substitui nenhum arquivo existente.
//
// V25: namespace corrigido para Aura.QuantX.Desktop (casa com o projeto).
// Ja integrado no ServiceSupervisor.MonitorServicesAsync — instalar os dois
// arquivos JUNTOS.
//
// Modos:
// Equal — exp/2 fixo + exp/2 aleatorio (recomendado p/ restart local)
// Full — uniforme(0, exp) — maxima dispersao (clientes distribuidos)
// Decorrelated — uniforme(base, 3x ultimo)
//
// Validacao isolada (PowerShell):
// Add-Type -Path "desktop\BackoffPolicy.cs"
// [Aura.QuantX.Desktop.BackoffPolicy]::RunSelfTest()
//
// Thread-safe (lock por instancia). Corpo compativel com C# 5 (PowerShell 5.1)
// e com .NET 6 (block namespace compila em ambos).
// ============================================================================
using System;
using System.Threading;

namespace Aura.QuantX.Desktop
{
    public enum BackoffJitterMode
    {
        Equal = 0,
        Full = 1,
        Decorrelated = 2
    }

    public sealed class BackoffPolicy
    {
        private readonly object _gate = new object();
        private readonly Random _rng;
        private readonly long _baseMs;
        private readonly long _capMs;
        private readonly BackoffJitterMode _mode;
        private readonly long _resetAfterStableMs;

        private int _attempt;
        private long _lastDelayMs;
        private DateTime _lastDelayUtc = DateTime.MinValue;

        public long DelaysComputed;
        public long Resets;

        public BackoffPolicy(long baseMs = 1000, long capMs = 60000,
                             BackoffJitterMode mode = BackoffJitterMode.Equal,
                             int? seed = null, long resetAfterStableMs = 300000)
        {
            if (baseMs <= 0)
                throw new ArgumentOutOfRangeException("baseMs", "deve ser > 0");
            if (capMs < baseMs)
                throw new ArgumentOutOfRangeException("capMs", "deve ser >= baseMs");
            if (resetAfterStableMs < 0)
                throw new ArgumentOutOfRangeException("resetAfterStableMs", "deve ser >= 0");
            _baseMs = baseMs;
            _capMs = capMs;
            _mode = mode;
            _resetAfterStableMs = resetAfterStableMs;
            _rng = seed.HasValue ? new Random(seed.Value) : new Random();
        }

        public int CurrentAttempt
        {
            get { lock (_gate) { return _attempt; } }
        }

        public long NextDelayMs()
        {
            lock (_gate)
            {
                long exp = ExponentialMs(_attempt);
                long d;
                if (_mode == BackoffJitterMode.Full)
                {
                    d = NextLong(0, exp);
                }
                else if (_mode == BackoffJitterMode.Decorrelated)
                {
                    long lo = _baseMs;
                    long hiRaw = (_lastDelayMs <= 0) ? _baseMs * 3 : _lastDelayMs * 3;
                    long hi = (hiRaw > _capMs) ? _capMs : hiRaw;
                    d = (hi <= lo) ? lo : NextLong(lo, hi);
                }
                else // Equal
                {
                    d = exp / 2 + NextLong(0, exp / 2 + 1);
                }
                if (d > _capMs) d = _capMs;
                if (d < 0) d = 0;
                _attempt++;
                _lastDelayMs = d;
                _lastDelayUtc = DateTime.UtcNow;
                DelaysComputed++;
                return d;
            }
        }

        public void NotifyHealthy()
        {
            lock (_gate)
            {
                if (_attempt == 0) return;
                if (_lastDelayUtc == DateTime.MinValue) { _attempt = 0; return; }
                double stableMs = (DateTime.UtcNow - _lastDelayUtc).TotalMilliseconds;
                if (stableMs >= (double)_resetAfterStableMs)
                {
                    _attempt = 0;
                    _lastDelayMs = 0;
                    Resets++;
                }
            }
        }

        private long ExponentialMs(int attempt)
        {
            long d = _baseMs;
            for (int i = 0; i < attempt; i++)
            {
                if (d >= _capMs) return _capMs;
                if (d > _capMs / 2) return _capMs; // 2*d passaria do cap (overflow-safe)
                d *= 2;
            }
            return (d > _capMs) ? _capMs : d;
        }

        // chamado apenas sob _gate
        private long NextLong(long lo, long hiExclusive)
        {
            if (hiExclusive <= lo) return lo;
            double u = _rng.NextDouble();
            long d = lo + (long)(u * (double)(hiExclusive - lo));
            if (d < lo) d = lo;
            if (d >= hiExclusive) d = hiExclusive - 1;
            return d;
        }

        public static bool RunSelfTest()
        {
            int pass = 0, fail = 0;
            Action<string, bool> check = delegate(string name, bool cond)
            {
                Console.WriteLine("[{0}] {1}", cond ? "PASS" : "FAIL", name);
                if (cond) pass++; else fail++;
            };

            BackoffPolicy a = new BackoffPolicy(100, 1600, BackoffJitterMode.Equal, 42);
            BackoffPolicy b = new BackoffPolicy(100, 1600, BackoffJitterMode.Equal, 42);
            bool same = true;
            for (int i = 0; i < 12; i++)
            {
                if (a.NextDelayMs() != b.NextDelayMs()) same = false;
            }
            check("sequencia deterministica com seed", same);

            BackoffPolicy p = new BackoffPolicy(100, 1600, BackoffJitterMode.Equal, 7);
            bool bounds = true;
            for (int k = 0; k < 8; k++)
            {
                long exp = 100;
                for (int i = 0; i < k; i++) exp *= 2;
                if (exp > 1600) exp = 1600;
                long d = p.NextDelayMs();
                if (d < exp / 2 || d > exp) bounds = false;
            }
            check("Equal dentro de [exp/2, exp]", bounds);

            bool capped = true;
            for (int i = 0; i < 30; i++)
            {
                if (p.NextDelayMs() > 1600) capped = false;
            }
            check("cap respeitado", capped);

            BackoffPolicy pf = new BackoffPolicy(100, 1600, BackoffJitterMode.Full, 9);
            long first = pf.NextDelayMs();
            check("Full: primeira tentativa em [0, base]", first >= 0 && first <= 100);
            bool fb = true;
            for (int i = 0; i < 30; i++)
            {
                long d = pf.NextDelayMs();
                if (d < 0 || d > 1600) fb = false;
            }
            check("Full: sempre dentro de [0, cap]", fb);

            BackoffPolicy pd = new BackoffPolicy(100, 1600, BackoffJitterMode.Decorrelated, 13);
            bool db = true;
            for (int i = 0; i < 20; i++)
            {
                long d = pd.NextDelayMs();
                if (d < 100 || d > 1600) db = false;
            }
            check("Decorrelated dentro de [base, cap]", db);

            BackoffPolicy pr = new BackoffPolicy(100, 160000, BackoffJitterMode.Equal, 11, 1);
            for (int i = 0; i < 6; i++) pr.NextDelayMs();
            check("tentativas acumuladas", pr.CurrentAttempt == 6);
            Thread.Sleep(5);
            pr.NotifyHealthy();
            check("reset apos estabilidade", pr.CurrentAttempt == 0);
            long d0 = pr.NextDelayMs();
            check("pos-reset volta ao range inicial", d0 >= 50 && d0 <= 100);

            BackoffPolicy pt = new BackoffPolicy(50, 400, BackoffJitterMode.Equal);
            int violations = 0;
            Thread[] ts = new Thread[8];
            for (int t = 0; t < ts.Length; t++)
            {
                ts[t] = new Thread(delegate()
                {
                    for (int i = 0; i < 100; i++)
                    {
                        long d = pt.NextDelayMs();
                        if (d < 0 || d > 400) Interlocked.Increment(ref violations);
                    }
                });
            }
            for (int t = 0; t < ts.Length; t++) ts[t].Start();
            for (int t = 0; t < ts.Length; t++) ts[t].Join();
            check("thread-safe: 800 delays sem violacao",
                  violations == 0 && pt.DelaysComputed == 800);

            bool threw = false;
            try { new BackoffPolicy(0, 100, BackoffJitterMode.Equal); }
            catch (ArgumentOutOfRangeException) { threw = true; }
            check("parametros invalidos rejeitados", threw);

            Console.WriteLine(fail == 0
                ? "ALL TESTS PASSED - BackoffPolicy.cs"
                : "SELF-TEST FALHOU: " + fail);
            return fail == 0;
        }
    }
}

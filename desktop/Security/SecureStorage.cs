/*
 * AURA QUANT-X V25 — SecureStorage: cofre de credenciais via DPAPI.
 * Criptografa tokens com a chave do usuário Windows (CurrentUser).
 * O arquivo armazenado contém somente ciphertext; chaves com traversal são recusadas.
 */
using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace Aura.QuantX.Desktop.Security;

public static class SecureStorage
{
    private static readonly string Dir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "AURA_QUANT_X", "secure");

    static SecureStorage()
    {
        Directory.CreateDirectory(Dir);
    }

    private static string SafePath(string key)
    {
        if (string.IsNullOrWhiteSpace(key) ||
            key.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 ||
            key is "." or ".." ||
            Path.GetFileName(key) != key)
            throw new ArgumentException("key inválida", nameof(key));
        return Path.Combine(Dir, key + ".bin");
    }

    /// <summary>Criptografa e salva um valor usando DPAPI CurrentUser.</summary>
    public static void Store(string key, string value)
    {
        var path = SafePath(key);
        var plain = Encoding.UTF8.GetBytes(value ?? string.Empty);
        var cipher = ProtectedData.Protect(plain, null, DataProtectionScope.CurrentUser);
        var temporary = path + ".tmp";
        File.WriteAllBytes(temporary, cipher);
        File.Move(temporary, path, true);
    }

    /// <summary>Descriptografa e retorna o valor; null se ausente ou inválido.</summary>
    public static string? Retrieve(string key)
    {
        string path;
        try { path = SafePath(key); }
        catch (ArgumentException) { return null; }
        if (!File.Exists(path)) return null;
        try
        {
            var cipher = File.ReadAllBytes(path);
            var plain = ProtectedData.Unprotect(cipher, null, DataProtectionScope.CurrentUser);
            return Encoding.UTF8.GetString(plain);
        }
        catch (CryptographicException) { return null; }
        catch (IOException) { return null; }
    }

    /// <summary>Remove um valor do cofre.</summary>
    public static void Delete(string key)
    {
        string path;
        try { path = SafePath(key); }
        catch (ArgumentException) { return; }
        try { if (File.Exists(path)) File.Delete(path); }
        catch (IOException) { }
    }

    /// <summary>Verifica se um valor existe.</summary>
    public static bool Exists(string key)
    {
        try { return File.Exists(SafePath(key)); }
        catch (ArgumentException) { return false; }
    }
}

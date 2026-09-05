# Requires openssl (Git Bash) on Windows
$Out = if ($args[0]) { $args[0] } else { "." }
openssl req -x509 -newkey rsa:2048 -keyout "$Out\key.pem" -out "$Out\cert.pem" -days 365 -nodes -subj "/CN=aura-grid-lab"
Write-Host "Wrote cert.pem key.pem — lab TLS only"

import os
import ipaddress
import socket
import subprocess
import re
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import datetime

base_dir = os.path.dirname(os.path.abspath(__file__))
cert_path = os.path.join(base_dir, 'cert.pem')
key_path = os.path.join(base_dir, 'key.pem')

lan_ips = set()
lan_ips.add(ipaddress.IPv4Address("127.0.0.1"))

try:
    result = subprocess.run(
        ['powershell', '-c', '(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notmatch \"^127\\.|^169\\.254\\.\" }).IPAddress'],
        capture_output=True, text=True, timeout=5
    )
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if line:
            try:
                lan_ips.add(ipaddress.IPv4Address(line))
            except (ipaddress.AddressValueError, ValueError):
                pass
except Exception:
    pass

try:
    hostname = socket.gethostname()
    for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
        ip = info[4][0]
        if not ip.startswith('127.'):
            lan_ips.add(ipaddress.IPv4Address(ip))
except Exception:
    pass

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

subject = issuer = x509.Name([
    x509.NameAttribute(NameOID.COUNTRY_NAME, "AR"),
    x509.NameAttribute(NameOID.COMMON_NAME, "VAN Dev"),
])

sans = [x509.DNSName("localhost")]
for ip in sorted(lan_ips, key=str):
    sans.append(x509.IPAddress(ip))

cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
    .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
    .add_extension(
        x509.SubjectAlternativeName(sans),
        critical=False,
    )
    .sign(key, hashes.SHA256())
)

with open(cert_path, "wb") as f:
    f.write(cert.public_bytes(serialization.Encoding.PEM))
with open(key_path, "wb") as f:
    f.write(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))

print(f"Certificado generado con SANs:")
for san in sans:
    print(f"  {san}")
print(f"\n  {cert_path}")
print(f"  {key_path}")
print("\nUsa: SSL_ENABLED=true python backend/app.py")

"""Inicia manualmente el puente local con NEXUS. No se inicia con la app."""
import time
from src.integrations.nexus_bridge import NexusBridge


def main():
    bridge = NexusBridge()
    token = bridge.start()
    print("Puente local activo en http://127.0.0.1:8765")
    print("Token guardado en data/nexus_bridge.token")
    print("No compartas el token. Pulsa Ctrl+C para detener el puente.")
    print(f"Token: {token}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        bridge.stop()
        print("Puente detenido.")


if __name__ == "__main__":
    main()

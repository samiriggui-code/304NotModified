"""Outils en ligne de commande.

python -m app.cli set-password [fichier]   # change le mot de passe du tableau de bord dans le fichier
                                           # de réglages (par défaut .env ; sur le VPS :
                                           # /etc/304notmodified.env), puis redémarrer l'API
python -m app.cli hash-password            # affiche seulement l'empreinte, à recopier à la main
"""

import getpass
import os
import secrets
import sys
import tempfile
from pathlib import Path

from .admin_auth import hash_password


def ask_password() -> str | None:
    password = getpass.getpass("Nouveau mot de passe du tableau de bord : ")
    if len(password) < 12:
        print("Refusé : au moins 12 caractères.", file=sys.stderr)
        return None
    if getpass.getpass("Encore une fois : ") != password:
        print("Les deux saisies diffèrent.", file=sys.stderr)
        return None
    return password


def set_env_value(path: Path, name: str, value: str) -> None:
    """Remplace (ou ajoute) NAME='value' dans le fichier, sans toucher aux autres lignes."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    lines = [line for line in lines if not line.startswith(f"{name}=")]
    lines.append(f"{name}='{value}'")
    # Écriture atomique, en gardant les droits du fichier d'origine (secret : lisible par root et nm304).
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as tmp:
        tmp.write("\n".join(lines) + "\n")
    os.chmod(tmp.name, mode)
    if path.exists():
        stat = path.stat()
        try:
            os.chown(tmp.name, stat.st_uid, stat.st_gid)
        except PermissionError:
            pass
    os.replace(tmp.name, path)


def main(argv: list[str]) -> int:
    command = argv[:1]
    if command == ["hash-password"]:
        password = ask_password()
        if password is None:
            return 1
        print(hash_password(password))
        return 0
    if command == ["set-password"]:
        path = Path(argv[1] if len(argv) > 1 else ".env")
        if path.exists() and not os.access(path, os.W_OK):
            print(f"Impossible d'écrire dans {path} : relancez avec sudo.", file=sys.stderr)
            return 1
        password = ask_password()
        if password is None:
            return 1
        set_env_value(path, "ADMIN_PASSWORD_HASH", hash_password(password))
        print(f"Mot de passe changé dans {path}. Redémarrez l'API pour qu'il soit pris en compte.")
        return 0
    if command == ["reset-admin"]:
        # Sans saisie : génère un mot de passe, enregistre son empreinte (et l'e-mail s'il est donné),
        # puis l'affiche une seule fois. Utilisé par deploy/reset-admin.sh.
        path = Path(argv[1] if len(argv) > 1 else ".env")
        if path.exists() and not os.access(path, os.W_OK):
            print(f"Impossible d'écrire dans {path} : relancez avec sudo.", file=sys.stderr)
            return 1
        if len(argv) > 2:
            set_env_value(path, "ADMIN_EMAIL", argv[2].strip().lower())
        password = secrets.token_urlsafe(15)
        set_env_value(path, "ADMIN_PASSWORD_HASH", hash_password(password))
        print(password)
        return 0
    print(__doc__.strip())
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

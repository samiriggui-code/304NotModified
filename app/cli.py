"""Outils en ligne de commande.

python -m app.cli hash-password     # demande un mot de passe, affiche son empreinte pour ADMIN_PASSWORD_HASH
"""

import getpass
import sys

from .admin_auth import hash_password


def main(argv: list[str]) -> int:
    if argv[:1] != ["hash-password"]:
        print(__doc__.strip())
        return 1
    password = getpass.getpass("Nouveau mot de passe du tableau de bord : ")
    if len(password) < 12:
        print("Refusé : au moins 12 caractères.", file=sys.stderr)
        return 1
    if getpass.getpass("Encore une fois : ") != password:
        print("Les deux saisies diffèrent.", file=sys.stderr)
        return 1
    print(hash_password(password))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

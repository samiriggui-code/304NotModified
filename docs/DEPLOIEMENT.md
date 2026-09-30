# Mettre 304NotModified en ligne sur le VPS

Prévu pour un VPS **Debian 12+ ou Ubuntu 22.04+** (testé pour Ubuntu 24.04), avec le nom de
domaine déjà pointé dessus (enregistrement A vers l'adresse IP du VPS), et **le Traefik déjà en
place sur le VPS** (conteneur Docker de `gsms-deploy`). Le HTTPS est assuré par ce Traefik et ses
certificats Let's Encrypt : le script n'installe **ni Caddy, ni nginx, ni un autre Traefik**. Il
dépose seulement un fichier de routes `304notmodified.yaml` dans le dossier dynamique de Traefik. Prévoir au moins **1 Go de mémoire** : la compilation du tableau de bord
en demande ; sur un petit VPS, le script ajoute un fichier d'échange de 2 Go.

Ce qui sera installé :

| Adresse | Service | Pour qui |
|---|---|---|
| `https://304notfound.com/v1/…`, `/llms.txt`, `/docs` | API et MCP (Python, port local 8304) | les agents IA |
| `https://304notfound.com/admin` | tableau de bord (Next.js Metronic, port local 3304) | vous seul, avec e-mail et mot de passe |
| `/internal/…` | données du tableau de bord | **jamais routé par Traefik** : seul le tableau de bord, sur le serveur, y accède |

- le code dans `/opt/304notmodified`, les deux services tournent en permanence sous un utilisateur
  dédié sans droits (`nm304`) et redémarrent tout seuls ;
- la base de données dans `/var/lib/304notmodified` ;
- les réglages secrets dans `/etc/304notmodified.env` (jamais dans git) ;
- Node.js 22 dans `/opt/node` (téléchargé sur nodejs.org, empreinte vérifiée) ;
- les routes HTTPS dans le dossier dynamique de Traefik : le script le retrouve tout seul (montage
  du conteneur Traefik), ainsi que le nom du certificat (`le` chez vous) et l'adresse du réseau
  Docker de Traefik, sur laquelle écoutent les deux services (joignable par Traefik, pas depuis
  Internet).

Au départ, **aucune clé Anthropic** n'est mise : aucune recherche payante, les questions sont
seulement enregistrées. Cela permet de vérifier que tout marche sans dépenser.

## Étape 1 : préparer l'accès au dépôt privé

Connectez-vous au VPS en SSH, puis collez :

```bash
sudo apt-get update && sudo apt-get install -y git
sudo useradd --system --create-home --shell /usr/sbin/nologin nm304
sudo -u nm304 mkdir -p -m 700 /home/nm304/.ssh
sudo -u nm304 ssh-keygen -q -t ed25519 -N "" -C "304notmodified-vps" -f /home/nm304/.ssh/id_ed25519
sudo cat /home/nm304/.ssh/id_ed25519.pub
```

La dernière commande affiche une ligne qui commence par `ssh-ed25519`. C'est une clé **publique**,
sans danger.

## Étape 2 : autoriser le VPS à lire le dépôt (sur GitHub)

1. Ouvrez https://github.com/samiriggui-code/304NotModified/settings/keys/new
2. **Title** : `VPS 304notmodified`
3. **Key** : collez la ligne `ssh-ed25519 …`
4. Laissez **« Allow write access » décoché** (le VPS pourra lire le code, jamais le modifier).
5. Cliquez sur **Add key**.

## Étape 3 : installer

De retour sur le VPS (mettez votre e-mail : ce sera votre identifiant de connexion) :

```bash
sudo -u nm304 sh -c 'ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts'
sudo install -d -o nm304 -g nm304 /opt/304notmodified
sudo -u nm304 git clone git@github.com:samiriggui-code/304NotModified.git /opt/304notmodified
sudo bash /opt/304notmodified/deploy/install.sh 304notfound.com vous@exemple.fr
```

Le script vérifie que le domaine pointe bien sur le VPS,
que Traefik tourne et trouve sa configuration, installe tout (compter plusieurs minutes
pour la compilation du tableau de bord), dépose les routes, vérifie que l'API répond, que le
tableau de bord répond, que `/internal` est bien bloqué et que l'API n'est pas joignable en direct, puis affiche
**une seule fois** votre mot de passe. Notez-le aussitôt dans un gestionnaire de mots de passe.

Ensuite : **https://304notfound.com/admin**

Le script peut être relancé sans risque. S'il s'arrête, il explique pourquoi en français.

## Mettre à jour après un changement du code

```bash
sudo bash /opt/304notmodified/deploy/update.sh
```

## Changer le mot de passe du tableau de bord

```bash
cd /opt/304notmodified && sudo -u nm304 .venv/bin/python -m app.cli hash-password
sudo nano /etc/304notmodified.env        # remplacer ADMIN_PASSWORD_HASH='…' par la nouvelle empreinte
sudo systemctl restart 304notmodified
```

Pour déconnecter toutes les sessions ouvertes, changer aussi `SESSION_SECRET` (texte aléatoire long).

## Activer les vraies recherches (quand vous le décidez)

Cela coûte de l'argent à chaque recherche fraîche. Avant tout, **fixez une limite de dépense
mensuelle** dans la console Anthropic. Puis :

```bash
sudo nano /etc/304notmodified.env        # remplir ANTHROPIC_API_KEY='...'
sudo systemctl restart 304notmodified
```

## En cas de problème

```bash
sudo systemctl status 304notmodified 304notmodified-admin     # les services tournent-ils ?
sudo journalctl -u 304notmodified -n 50                       # messages de l'API
sudo journalctl -u 304notmodified-admin -n 50                 # messages du tableau de bord
docker logs --tail 50 $(docker ps --format '{{.Names}}' | grep -i traefik | head -1)   # messages de Traefik (HTTPS)
```

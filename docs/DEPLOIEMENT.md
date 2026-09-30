# Mettre 304NotModified en ligne sur le VPS

Prévu pour un VPS **Debian 12+ ou Ubuntu 22.04+**, avec le nom de domaine déjà pointé dessus
(enregistrement A vers l'adresse IP du VPS). Le HTTPS est automatique (Caddy + Let's Encrypt).

Ce qui sera installé :

- le service dans `/opt/304notmodified`, qui tourne en permanence sous un utilisateur dédié
  sans droits (`nm304`) et redémarre tout seul ;
- la base de données dans `/var/lib/304notmodified` ;
- les réglages secrets dans `/etc/304notmodified.env` (jamais dans git) ;
- Caddy devant, pour le HTTPS.

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

De retour sur le VPS (remplacez le nom de domaine si besoin) :

```bash
sudo -u nm304 sh -c 'ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts'
sudo install -d -o nm304 -g nm304 /opt/304notmodified
sudo -u nm304 git clone git@github.com:samiriggui-code/304NotModified.git /opt/304notmodified
sudo bash /opt/304notmodified/deploy/install.sh 304notmodified.com
```

Le script vérifie que le domaine pointe bien sur le VPS et que les ports 80/443 sont libres,
installe tout, puis affiche **une seule fois** le mot de passe du tableau de bord. Notez-le
aussitôt dans un gestionnaire de mots de passe.

Ensuite : **https://304notmodified.com/admin**

Le script peut être relancé sans risque. S'il s'arrête, il explique pourquoi en français.

## Mettre à jour après un changement du code

```bash
sudo bash /opt/304notmodified/deploy/update.sh
```

## Activer les vraies recherches (quand vous le décidez)

Cela coûte de l'argent à chaque recherche fraîche. Avant tout, **fixez une limite de dépense
mensuelle** dans la console Anthropic. Puis :

```bash
sudo nano /etc/304notmodified.env        # remplir ANTHROPIC_API_KEY=...
sudo systemctl restart 304notmodified
```

## En cas de problème

```bash
sudo systemctl status 304notmodified     # le service tourne-t-il ?
sudo journalctl -u 304notmodified -n 50  # ses derniers messages
sudo journalctl -u caddy -n 50           # ceux du HTTPS
```

# YourGoal 🎯

> **Note** : Cette application a été réalisée intégralement en **Vibe Coding** via OpenCode + DeepSeek V4.

![Capture d'écran](Capture.jpg)

**YourGoal** est une application web ultra-simple de suivi de points pour enfants. Les parents attribuent des points, les enfants consultent leur solde et voient le tableau des valeurs d'échange.

---

## Comment ça marche

### Pour les enfants

1. Se connectent avec leur identifiant
2. Voient **un écran unique** : leur nombre de points en gros chiffre
3. Cliquent sur **"Tableau des Valeurs"** pour voir ce que valent leurs points

### Pour les parents

1. Voient la liste de leurs enfants avec **+** et **-** pour ajuster les points
2. Cliquent sur **"Valeurs"** pour définir le tableau d'équivalence (ex: 10 points = 1 €)
3. Cliquent sur **"Utilisateurs"** pour ajouter/supprimer des enfants

### Exemple

- Julie range sa chambre → le parent clique **+** → Julie passe de 0 à 1 point
- Julie accumule 10 points → elle demande 1 € → le parent clique **-** → Julie repasse à 0 point

**Rien de plus.** Pas de listes de tâches, pas de compteurs, pas d'alertes, pas d'historique.

---

## Guide utilisateur

### Premier lancement

1. Ouvrez `http://localhost:5001`
2. Cliquez sur **S'inscrire** → choisissez **Parent** (premier = admin)
3. Créez votre compte

### Ajouter un enfant

1. Cliquez sur **Utilisateurs** dans l'en-tête
2. Remplissez le login, mot de passe, prénom → **Ajouter**
3. L'enfant peut maintenant se connecter

### Donner/retirer des points

1. Connecté en tant que parent, vous voyez tous les enfants
2. Cliquez **+** pour ajouter 1 point, **-** pour en retirer 1

### Configurer le tableau des valeurs

1. Cliquez sur **Valeurs** dans l'en-tête
2. Ajoutez des lignes : nom, points, unité (optionnelle)
3. Exemple : `Euro | 10 pts | €` ou `Temps d'écran | 15 pts | minutes`
4. Cliquez **Enregistrer**

---

## Stack technique

| Composant | Technologie |
|-----------|------------|
| Backend | Python / Flask |
| Frontend | HTML, JavaScript |
| Style | Glassmorphism, responsive |
| Stockage | Fichier JSON (`server_data.json`) |
| PWA | manifest.json, Service Worker |
| Conteneurisation | Docker |

---

## Installation

```bash
pip install -r requirements.txt
python server.py
```

Accès : `http://localhost:5001`

### Docker

```bash
docker-compose up -d
```

Accès : `http://votre-ip:5001`

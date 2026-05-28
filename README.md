# YourGoal 🎯

Application web de récompenses pour enfants — Gestion de tâches, points et compteurs.

Les parents créent des tâches, les enfants les accomplissent, gagnent des points et les échangent contre des récompenses (temps d'écran, argent, etc.).

## Fonctionnalités

- **Tâches** : Création, assignment, cycle complet (proposée → en cours → terminée → validée/refusée)
- **Tâches récurrentes** : Se réinitialisent automatiquement après validation
- **Points** : Gagnés sur validation, dépensés sur des compteurs
- **Compteurs** : Temps d'écran, MoneyWalky, etc. — configurables avec prix en points
- **Avatars** : 30 émojis animaux, choix par enfant et parent
- **Alertes** : Messages parents → enfants avec accusé de lecture
- **Historique** : 40 dernières tâches complétées par enfant
- **Multi-utilisateurs** : Admin, parents, enfants — rôles distincts

## Stack

- **Backend** : Python / Flask
- **Frontend** : HTML / JS (IIFE) — Glassmorphism, PWA
- **Stockage** : Fichier JSON (server_data.json)
- **Déploiement** : Docker — port 5001

## Installation

```bash
docker-compose up -d
# http://localhost:5001
```

Déploiement ZimaOS : voir `ZimaOS_Deploy.txt`

Documentation complète : `Description.txt`

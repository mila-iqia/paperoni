
Bienvenue sur Paperoni ! Paperoni est un outil de gestion d'articles.

# Recherche {: #search}

L'interface [Recherche](/search) permet de chercher dans la base d'articles de
Paperoni. La recherche se fait au fil de la frappe (avec un court délai). Les
résultats sont triés pour afficher les publications les plus récentes en premier.

* **Titre** : Recherche par titre d'article.
* **Auteur** : Recherche par auteur. Il n'est pas encore possible de chercher
  plusieurs auteurs. Cette fonctionnalité sera probablement ajoutée à l'avenir.
* **Institution** : Recherche par affiliation ou institution de l'auteur.
* **Conférence** : Recherche par lieu de publication (conférence ou revue scientifique).
  Les alias ne sont pas
  toujours pris en compte ; vous devrez peut-être chercher « Neural Information
  Processing Systems » au lieu de « NeurIPS » ou l'inverse.
* **Date de début/fin** : Recherche d'articles ayant au moins une parution entre
  ces dates. Par exemple, un article avec une prépublication en 2022 et une
  publication en 2023 apparaîtra pour 2022 et 2023.
* **Évalué par les pairs** : Cochez cette case pour n'afficher que les
  publications évaluées par les pairs.

## Filtrage par clic

Dans les résultats, vous pouvez cliquer sur un nom d'auteur, une institution,
un lieu ou une année pour filtrer immédiatement les résultats par cette valeur.

## Bouton Modifier

Si vous avez les droits de validation, une icône de modification (<img src="/assets/pen.svg"
alt="modifier" style="height:1em; vertical-align:middle">) apparaît à côté de
chaque titre. Un clic ouvre la page d'édition de l'article dans un nouvel
onglet, où vous pouvez modifier le titre, les auteurs, les lieux et autres champs.

# Modification des articles {: #edit}

L'interface d'édition permet de modifier toutes les données d'un article :
titre, résumé, auteurs et affiliations, parutions (lieux et dates), sujets,
liens et drapeaux. Vous pouvez aussi créer un nouvel article depuis
[/edit/new](/edit/new), ou supprimer un article.

Depuis la page de recherche, cliquez sur l'icône d'édition d'un article pour
ouvrir sa page de modification.

# Exclusions {: #exclusions}

La page [Exclusions](/exclusions) permet de gérer une liste d'identifiants
d'articles exclus. Les identifiants exclus (ex. `arxiv:1234.5678`,
`doi:10.1234/...`) sont filtrés lors de la découverte d'articles. Vous pouvez
ajouter des exclusions une par une ou en lot (une par ligne), et les retirer
au besoin.

# Focus {: #focuses}

La page [Focus](/focuses) permet aux administrateurs de configurer les focus
de recherche qui pilotent la découverte et le scoring des articles. Deux onglets :

* **Principal** : Focus principaux qui définissent les centres d'intérêt (auteurs,
  lieux, sujets, etc.) et leurs scores associés.
* **Auto** : Focus générés automatiquement. Utilisez le bouton « Autogénérer »
  pour les régénérer à partir de la collection actuelle.

Chaque focus a un type, un nom, un score et une option pour indiquer s'il
pilote la découverte de nouveaux articles.

# Jeu de travail {: #workset}

La page [Jeu de travail](/workset) affiche les articles du jeu de travail
actuel, scorés et classés selon les focus configurés. Les articles sont
affichés avec leurs scores et métadonnées ; les liens PDF sont disponibles
lorsque le texte intégral a été localisé.

# Groupe récent {: #latest-group}

La page [Groupe récent](/latest-group) permet de découvrir les articles
récemment publiés. Vous pouvez définir une date d'ancrage et une fenêtre
(jours en arrière/avant) pour trouver de nouveaux articles. La date d'ancrage
est le centre de la fenêtre : Paperoni cherche entre `date d'ancrage - jours
en arrière` et `date d'ancrage + jours en avant` (inclus). Par exemple, si la
date d'ancrage est `2026-02-19`, avec `jours en arrière = 30` et `jours en
avant = 0`, l'intervalle est `2026-01-20` à `2026-02-19`. Avec `jours en avant
= 7`, l'intervalle devient `2026-01-20` à `2026-02-26`. Les résultats sont
séparés en publications évaluées par les pairs et prépublications. Une
newsletter peut être générée à partir de ces résultats.

# Capacités {: #capabilities}

La page [Capacités](/capabilities) permet aux administrateurs de gérer les
comptes utilisateurs et leurs permissions. Vous pouvez ajouter des
utilisateurs et attribuer ou révoquer des capacités comme `search`, `validate`,
`admin`, etc. Les capacités implicites (dérivées de la hiérarchie) sont
affichées avec les capacités attribuées directement.

# Rapports {: #reports}

La page [Rapports](/report) liste les rapports d'erreur disponibles générés
à partir des journaux de traitement. Chaque rapport affiche les erreurs groupées
par type, avec tracebacks et nombre d'occurrences. Utile principalement aux
développeurs et administrateurs pour le débogage du traitement des données.

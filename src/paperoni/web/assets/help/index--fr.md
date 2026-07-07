
Bienvenue sur Paperoni ! Paperoni est un outil de gestion d'articles développé à Mila.

## Table des matières

1. **[Rechercher des articles](#search)**
1. **[Ajouter des articles](#new)**
1. **[Modifier des articles](#edit)**

Voir également [l'aide de l'interface de validation](/help/validation) et de [l'interface d'administration](/help/admin).

## Rechercher des articles {: #search}

L'interface [Recherche](/search) permet de chercher dans la base d'articles de
Paperoni. La recherche se fait au fil de la frappe (avec un court délai). Les
résultats sont triés pour afficher les publications les plus récentes en premier.

* **Titre** : Recherche par titre d'article.
* **Auteur** : Recherche par nom ou courriel d'auteur (un seul auteur peut être précisé).
* **Institution** : Recherche par affiliation ou institution de l'auteur.
* **Conférence** : Recherche par lieu de publication. Nous faisons de notre mieux pour normaliser les noms de lieux, mais il arrive qu'un même lieu soit répertorié sous plusieurs orthographes.
* **Sujet** : Recherche par sujet. Ceux-ci ne sont pas nécessairement cohérents ni complets sur l'ensemble de la collection.
* **Date de début/fin** : Recherche d'articles ayant au moins une parution entre
  ces dates. Par exemple, un article avec une prépublication en 2022 et une
  publication en 2023 apparaîtra pour 2022 et 2023.
* **Type** : Filtre les articles évalués par les pairs, les prépublications ou les articles d'atelier.
* **Évalué par les pairs** : Cochez cette case pour n'afficher que les
  publications évaluées par les pairs.

Par défaut, Paperoni effectue une recherche par sous-chaîne. Vous pouvez préfixer une recherche par « = » pour effectuer une recherche exacte.

### Filtrage par clic

Dans les résultats, vous pouvez cliquer sur un nom d'auteur, une institution,
un lieu ou une année pour filtrer immédiatement les résultats par cette valeur.

### Bouton Modifier

Une icône de modification (<img src="/assets/pen.svg" alt="modifier" style="height:1em; vertical-align:middle">) apparaît à côté de chaque titre d'article. Un clic ouvre la [page d'édition](#edit) de l'article dans un nouvel onglet, où vous pouvez suggérer des modifications à son titre, ses auteurs, ses lieux et autres champs.


## Ajouter des articles {: #new}

[L'interface d'ajout d'articles](/edit/new) permet de suggérer de nouveaux articles. À moins que vous n'ayez le rôle de *validateur*, ces suggestions n'apparaîtront pas immédiatement dans la base de données, mais iront plutôt dans une file d'attente en attente d'approbation. L'article peut mettre quelques jours à apparaître.

**Avant de suggérer un article,** veuillez vérifier s'il ne se trouve pas déjà dans la base de données au moyen de l'interface de [recherche](/search).

### Remplir

En haut de l'interface, vous verrez une section Remplir où vous pouvez coller un lien vers l'article (vous pouvez en coller plusieurs, séparés par des virgules). Paperoni lira les métadonnées et remplira le formulaire pour vous. Les liens autorisés sont :

* **[arxiv](https://arxiv.org)** : ex. `https://arxiv.org/abs/1810.11530` ou `arxiv:1810.11530`
* **DOI** : ex. `doi:10.1109/comst.2024.3450292`
* **[Semantic Scholar](https://www.semanticscholar.org/)** : ex. `https://www.semanticscholar.org/paper/9f1ce3ff55eb559e00df33fa40ee6ecd6a2a54f1` ou `semantic_scholar:9f1ce3ff55eb559e00df33fa40ee6ecd6a2a54f1`

Cela ne fait que remplir le formulaire, rien n'est soumis. Vous pouvez vérifier ce qui a été rempli, corriger les erreurs, ajouter les lieux manquants, etc.

### Soumettre

Une fois terminé, cliquez simplement sur le bouton `Suggérer l'article`, en bas à droite. Cela placera l'article dans une file d'attente en vue de sa révision ; il est donc normal que vous ne le voyiez pas pendant un moment lorsque vous cherchez des articles juste après l'avoir suggéré.


## Modification des articles {: #edit}

L'interface d'édition permet de suggérer des changements à toutes les données associées à un article :
titre, résumé, auteurs et affiliations, parutions (lieux et dates), sujets,
liens et drapeaux. Vous pouvez aussi créer un nouvel article depuis
[/edit/new](/edit/new), ou supprimer un article.

Depuis la page de recherche, cliquez sur l'icône d'édition (<img src="/assets/pen.svg" alt="modifier" style="height:1em; vertical-align:middle">) à côté du titre d'un article pour ouvrir sa page de modification.


## API {: #api-token}

Paperoni dispose d'une API que vous pouvez utiliser pour obtenir des données par programmation. Pour l'utiliser, vous avez besoin d'un jeton (token) porteur.

1. **Obtenir un jeton** : Ouvrez la page [Jeton](/token). Connectez-vous avec
   Google lorsque demandé. À la fin du processus, la page affichera votre jeton
   — copiez-le et conservez-le de manière sécurisée.

2. **Utiliser le jeton** : Envoyez-le dans l'en-tête `Authorization` sous la
   forme `Bearer VOTRE_JETON`.

Exemple — recherche (10 premiers résultats) :

```
curl -H 'Authorization: Bearer VOTRE_JETON' \
  'https://paperoni.mila.quebec/api/v1/search?limit=10&offset=0'
```

Remplacez `VOTRE_JETON` par le jeton copié et adaptez l'URL de base si vous
utilisez une autre instance Paperoni.

Pour la référence complète de l'API REST (endpoints, paramètres, schémas),
consultez la [documentation API](/docs).

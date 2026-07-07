
Les fonctionnalités de cette page requièrent la capacité *admin*.

## Table des matières

1. **[Exclusions](#exclusions)**
1. **[Jeu de travail](#workset)**
1. **[Capacités](#capabilities)**
1. **[Rapports](#reports)**


## Exclusions {: #exclusions}

La page [Exclusions](/exclusions) permet de gérer une liste d'identifiants d'articles exclus. Les identifiants exclus (ex. `arxiv:1234.5678`, `doi:10.1234/...`) sont filtrés lors de la découverte d'articles. Vous pouvez ajouter des exclusions une par une ou en lot (une par ligne), et les retirer au besoin.


## Jeu de travail {: #workset}

La page [Jeu de travail](/workset) affiche les articles du jeu de travail
actuel, scorés et classés selon leur pertinence par rapport aux focus configurés. Les articles sont
affichés avec leurs scores et métadonnées ; les liens PDF sont disponibles
lorsque le texte intégral a été localisé.


## Capacités {: #capabilities}

La page [Capacités](/capabilities) permet aux administrateurs de gérer les comptes utilisateurs et leurs permissions. Vous pouvez ajouter des utilisateurs et attribuer ou révoquer des capacités comme `search`, `validate`, `admin`, etc. Les capacités implicites (dérivées de la hiérarchie des capacités) sont affichées visuellement à côté des capacités attribuées directement.


## Rapports {: #reports}

La page [Rapports](/report) liste les rapports d'erreur disponibles générés à partir des journaux de traitement. Chaque rapport affiche les erreurs groupées par type, avec tracebacks et nombre d'occurrences. Utile principalement aux développeurs et administrateurs pour le débogage du traitement des données.

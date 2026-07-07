
Les fonctionnalités de cette page requièrent la capacité *validateur*.

## Table des matières

1. **[Valider des articles](#pending)**
1. **[Focus](#focuses)**
1. **[Génération de newsletter](#latest-group)**


## Valider des articles {: #pending}

La liste des [articles en attente](/pending) contient les nouveaux articles et les modifications suggérées à des articles existants, soumis soit via l'[interface d'édition](/edit), soit par scraping automatisé.

Pour chaque article, **Approuvez** ou **Rejetez** l'ajout ou la modification à l'aide du bouton approprié, et une fois terminé, vous devez confirmer les changements au moyen du bouton en bas.

Si cela est plus efficace pour vous, vous pouvez utiliser les flèches haut et bas pour naviguer entre les articles, et les touches « A » et « R » de votre clavier pour accepter/rejeter.


## Focus {: #focuses}

La page [Focus](/focuses) permet de configurer les focus de recherche qui pilotent la découverte et le scoring des articles. Deux onglets :

* **Principal** : Focus principaux qui définissent les centres d'intérêt (auteurs, lieux, sujets, etc.) et leurs scores associés.
* **Auto** : Focus générés automatiquement. Utilisez le bouton « Autogénérer » pour les régénérer à partir de la collection actuelle.

Chaque focus a un type, un nom, un score et une option pour indiquer s'il
pilote la découverte de nouveaux articles.


## Génération de newsletter {: #latest-group}

La page [Groupe récent](/latest-group) permet de découvrir les articles récemment publiés. Vous pouvez définir une date d'ancrage et une fenêtre (jours en arrière/avant) pour trouver de nouveaux articles. La date d'ancrage est le centre de la fenêtre de recherche : Paperoni cherche entre `date d'ancrage - jours en arrière` et `date d'ancrage + jours en avant` (inclus). Par exemple, si la date d'ancrage est `2026-02-19`, avec `jours en arrière = 30` et `jours en avant = 0`, l'intervalle est `2026-01-20` à `2026-02-19`. Avec `jours en avant = 7`, l'intervalle devient `2026-01-20` à `2026-02-26`. Les résultats sont séparés en publications évaluées par les pairs et prépublications.

Une newsletter peut être générée à partir de ces résultats.

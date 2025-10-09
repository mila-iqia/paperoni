- Normalize known variants to their canonical forms.
  Use the standardized name in quotes for each known variant:
  - Normalize to "Mila" if the affiliation matches:
    - "MILA"
    - "Montreal Institute for Learning Algorithms"
    - "Quebec AI Institute"
    - "Mila AI Institute"
    - "Institut Québécois de l'Intelligence Artificielle"
    - "IQIA"
  - Normalize to "Université de Montréal" if the affiliation matches:
    - "University of Montreal"
    - "U. Montreal"
    - "Université Montréal"
    - "UdeM"
  - Normalize to "CIFAR" if the affiliation matches:
    - "CIFAR AI Chair"
    - "CIFAR Fellow"
- Handle compound or combined affiliations.
  If an affiliation contains multiple institutions joined by symbols (e.g., '-', '/', '|', ',', '–'):
  - Split the affiliation into individual components.
  - Normalize each part individually using the rules above.
  - Return a list of canonical names, omitting duplicates if the parts refer to the same institution.
  Examples:
  - "MILA / Université de Montréal" -> "Mila", "Université de Montréal"
  - "Quebec AI Institute | U. Montreal" -> "Mila", "Université de Montréal"
  - "Mila-IQIA" -> "Mila" (both are synonyms)

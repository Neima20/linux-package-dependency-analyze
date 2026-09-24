"""
pkg_analyzer.py
----------------
Outil d'analyse des paquets installés sur un système Linux (Debian/Ubuntu)
et de leurs relations de dépendance.

Fonctionnalités :
1. Lister les paquets installés (dpkg)
2. Récupérer les dépendances d'un paquet donné (apt-cache)
3. Construire un graphe de dépendances (networkx)
4. Identifier les paquets "essentiels" (beaucoup de paquets en dépendent)
   vs les paquets "feuilles" (aucun autre paquet n'en dépend)
5. Exporter le résultat en JSON
6. Représenter graphiquement l'arborescence des dépendances

Auteur : Neima Osman Ali
"""

import subprocess
import json
import networkx as nx
import matplotlib.pyplot as plt


# ---------------------------------------------------------------------
# 1. Lister les paquets installés
# ---------------------------------------------------------------------
def list_installed_packages():
    """
    Retourne la liste des noms de paquets actuellement installés,
    en utilisant dpkg.
    """
    result = subprocess.run(
        ["dpkg-query", "-W", "-f=${Package}\n"],
        capture_output=True, text=True, check=True
    )
    packages = result.stdout.strip().split("\n")
    return sorted(packages)


# ---------------------------------------------------------------------
# 2. Récupérer les dépendances directes d'un paquet
# ---------------------------------------------------------------------
def get_dependencies(package_name):
    """
    Retourne la liste des dépendances directes d'un paquet,
    en utilisant apt-cache depends.
    Ne garde que les dépendances obligatoires (on ignore Recommends,
    Suggests, etc.). Gère à la fois la sortie en anglais ("Depends:")
    et en français ("Dépend:"), selon la locale du système.
    """
    result = subprocess.run(
        ["apt-cache", "depends", package_name],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return []

    DEPENDS_LABELS = ("Depends:", "Dépend:")

    deps = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith(DEPENDS_LABELS):
            dep_name = line.split(":", 1)[1].strip()
            # apt-cache met parfois des <noms entre chevrons> pour les
            # dépendances virtuelles/alternatives : on les ignore.
            if not dep_name.startswith("<"):
                deps.append(dep_name)
    return deps


# ---------------------------------------------------------------------
# 3. Construire le graphe de dépendances
# ---------------------------------------------------------------------
def build_dependency_graph(root_packages, max_depth=2):
    """
    Construit un graphe orienté où une arête A -> B signifie
    "A dépend de B".
    Part d'une liste de paquets racines et explore leurs dépendances
    jusqu'à max_depth niveaux, pour éviter d'exploser sur tout le système.
    """
    graph = nx.DiGraph()
    visited = set()

    def explore(pkg, depth):
        if pkg in visited or depth > max_depth:
            return
        visited.add(pkg)
        graph.add_node(pkg)

        for dep in get_dependencies(pkg):
            graph.add_edge(pkg, dep)
            explore(dep, depth + 1)

    for pkg in root_packages:
        explore(pkg, 0)

    return graph


# ---------------------------------------------------------------------
# 4. Identifier les paquets essentiels vs optionnels
# ---------------------------------------------------------------------
def classify_packages(graph):
    """
    Un paquet est jugé "essentiel" si beaucoup d'autres paquets
    dépendent de lui (in-degree élevé dans le graphe).
    Un paquet "feuille" (optionnel) n'a aucune dépendance entrante :
    rien ne casse si on le supprime, à condition qu'il ne soit
    lui-même utilisé par rien d'autre en dehors du graphe étudié.
    """
    in_degrees = dict(graph.in_degree())
    sorted_pkgs = sorted(in_degrees.items(), key=lambda x: x[1], reverse=True)

    essential = [pkg for pkg, degree in sorted_pkgs if degree >= 2]
    optional = [pkg for pkg, degree in sorted_pkgs if degree == 0]

    return {
        "essential": essential,
        "optional": optional,
        "in_degrees": in_degrees
    }


# ---------------------------------------------------------------------
# 5. Export JSON
# ---------------------------------------------------------------------
def export_to_json(graph, classification, output_path="dependencies.json"):
    """
    Exporte le graphe et la classification dans un fichier JSON,
    format exploitable par un outil graphique externe si besoin.
    """
    data = {
        "nodes": list(graph.nodes()),
        "edges": [{"from": u, "to": v} for u, v in graph.edges()],
        "essential_packages": classification["essential"],
        "optional_packages": classification["optional"],
    }
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[OK] Export JSON -> {output_path}")


# ---------------------------------------------------------------------
# 6. Visualisation graphique
# ---------------------------------------------------------------------
def visualize_graph(graph, classification, output_path="dependencies.png"):
    """
    Dessine le graphe de dépendances. Les paquets essentiels sont
    affichés en rouge, les autres en bleu clair.
    """
    plt.figure(figsize=(12, 8))
    pos = nx.spring_layout(graph, k=0.6, seed=42)

    essential_set = set(classification["essential"])
    node_colors = [
        "#e74c3c" if node in essential_set else "#5dade2"
        for node in graph.nodes()
    ]

    nx.draw(
        graph, pos,
        with_labels=True,
        node_color=node_colors,
        node_size=1200,
        font_size=7,
        arrows=True,
        arrowsize=12,
        edge_color="#999999"
    )
    plt.title("Arborescence des dépendances de paquets")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    print(f"[OK] Graphique -> {output_path}")


# ---------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------
if __name__ == "__main__":
    # Paquets de départ à analyser (choisis-en des connus pour commencer)
    ROOT_PACKAGES = ["curl", "git"]

    print(f"Analyse des dépendances pour : {ROOT_PACKAGES}\n")

    graph = build_dependency_graph(ROOT_PACKAGES, max_depth=2)
    print(f"Graphe construit : {graph.number_of_nodes()} paquets, "
          f"{graph.number_of_edges()} relations de dépendance.\n")

    classification = classify_packages(graph)
    print("Paquets essentiels (utilisés par >= 2 autres) :")
    for pkg in classification["essential"]:
        print(f"  - {pkg} (utilisé par {classification['in_degrees'][pkg]} paquets)")

    print("\nPaquets feuilles (aucune dépendance entrante) :")
    for pkg in classification["optional"][:10]:
        print(f"  - {pkg}")

    export_to_json(graph, classification)
    visualize_graph(graph, classification)

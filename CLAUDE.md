# Smart CAPEX — contexte projet

Système de raisonnement par cas (CBR) qui prédit l'impact d'un nouveau site télécom (2G/3G/4G, Tunisie) à partir des lancements historiques les plus similaires. Phase 1, 55 features par site. Innovation clé: l'Angular Neighborhood Profile (ANP), qui distingue les sites de bord (extension de couverture) des sites d'infill (capacité).

## Sources de vérité

- Spec courante: `spec/smart_capex_spec_v1.0.md` (2026-10-24). Elle prime sur `spec/smart_capex_spec_v0.md` (v3.3, 2026-10-23, spec de base détaillée).
- Changements v0 → v1.0: `spec/CHANGELOG_v1.0.md`. Catalogue de features: `spec/smart_capex_data_catalog_phase1.md` et `spec/smart_capex_features.csv` (pas encore alignés sur 55 features).
- Le code suit les **noms de features de v1.0** (voir `core/models/features.py`), pas ceux de v0 (`t1_angular_entropy`, `coverage_ratio_pre`, etc.).
- `README.md` est en partie périmé (annonce 57/60 features, chemins `project_smart_capex/`, `.clinerules/` et `.tracking/` absents du dépôt).

## Architecture (Django + couche services)

- `core/`: app Django. Modèles, vues REST (lecture seule), sérialiseurs, commande `load_and_cluster`. Pas de logique métier ici.
- `services/`: toute la logique métier.
  - `models/preprocessing/`: `cellplan_loader`, `maos_loader`, `launch_detection`, `site_clustering`.
  - `models/features/anp.py`: calcul de l'ANP.
  - `models/similarity/`: `gower_distance`, `hierarchical_filter`, `kernel_weights`.
  - `models/prediction/`: **vide**.
  - `visualization/`: `dem_processor`, `geo_visualization/cluster_visualizer` (Folium).
  - `utils/geo_utils.py`: haversine, bearing, DEM, WorldCover.
- `frontend/`: Vue + Vite (carte des clusters). `smart_capex_backend/`: réglages Django.
- Règle d'architecture: pas de logique métier dans les modèles ni les vues; les vues appellent `services/`.
- Dépendances: `requirements.txt` (Polars, GeoPandas, Rasterio, scikit-learn, alphashape, Folium). Les données attendues sont dans `data/` (cellplan, maos, geographic), **absent du dépôt**; `config.example.yaml` décrit les chemins.

## État d'implémentation (au 2026-10-24)

Fait:
- Modèles Django pour les 6 groupes de features, `PreLaunchKPI`, `MAOSMonthlyKPI`, `Site`, `Cell`; migrations 0001 et 0002 (champs de clustering).
- Chargement du cell plan, puis clustering: dédup 50 m, DBSCAN (eps 2 km, min_samples 3, haversine), polygones alpha shape (α=0.05), sites de bord (< 111 m), validation de la boîte englobante de la Tunisie.
- Carte de clusters, heatmap `edge_score`, export GeoJSON; API `/api/sites/` (+ `clusters`, `cluster_stats`), `/api/cells/`, `/api/dem/*`.
- Calcul ANP, Gower, filtre hiérarchique, poids de noyau: classes écrites, pas encore branchées sur la base ni sur une API.

Pas fait:
- Extraction et persistance des features: Configuration, Géométrie (DEM), Clutter, Spatial, ANP, PreLaunch. Les tables existent, rien ne les remplit.
- `ClusterFeatures`: le clustering ne met à jour que `Site.cluster_id/is_cluster_edge/out_of_bounds`; les 5 autres features de cluster ne sont pas sauvegardées, et `traffic_gb`/`users` valent 0 en attendant les KPI.
- Nettoyage des labels par DiD, construction de la table d'entraînement (cas), prédiction, bootstrap CI, modèle linéaire local, `POST /api/predict/`, validation (LOO, ablation ANP).
- Données géographiques OSM/GHSL/WorldCover: non branchées dans un pipeline.
- Tests: `tests/` vide; `test_api.py` et `test_loader.py` sont des scripts ad hoc; migrations non testées.

## Écarts connus entre code et spec v1.0

1. **Poids de Gower** (`gower_distance.py`): configuration .28, prelaunch .27, spatial .20, anp .15, cluster .06, clutter .04 (somme 1.00, pas de groupe géométrie). La spec v0 donne 0.28/0.27/0.20/0.13/0.05/0.05 avec l'ANP inclus dans le spatial. À trancher.
2. **`edge_score`** (`anp.py`): combinaison pondérée (arc vide max, bins vides, uniformité, asymétrie, n_tier1). La spec v0 le définit comme `1 − entropie/log2(12)`; v1.0 dit seulement "composite".
3. **Types d'événements** (`launch_detection.py`): `CAPACITY_UPGRADE` et `REACTIVATION`, alors que la spec a `CAPACITY_ADD` et `TECH_SUNSET` (et le modèle `ConfigurationFeatures` suit la spec). La détection vérifie 2 mois d'historique (`lookback_months`), la spec exige tout l'historique.
4. **Noms de features et nombre**: v1.0 numérote jusqu'à 56 mais annonce 55 (somme 10+4+4+8+15+9+6 = 56 avant exclusion de `building_height`). `avg_building_height_m` reste dans le groupe Clutter.
5. `ClusterFeatures.cluster_id` a pour défaut 0 alors que le bruit vaut -1. `cluster_id` est traité comme catégoriel dans Gower.
6. La spec v1.0 est tronquée à la fin (modèle `ClusterFeatures` coupé après `cluster_avg_traffic_gb`).

## Conventions

- Données non commitées: `data/`, `.clinerules`, `.tracking` sont dans `.gitignore`. Le dépôt n'est pas initialisé en git ici.
- Fichier du cell plan attendu: `data/cellplan/Cell_Plan_Data_21102026.xlsx`.
- Charger les données et lancer le clustering: `python manage.py load_and_cluster` (ou `scripts/load_and_cluster.py`).
- Toute modification de spec: ajouter une entrée au changelog et garder le nom des features aligné entre spec, modèles et `GowerDistance`.

# Vision datasets: source evidence and Indian-food suitability

Inspected 2026-11-01. **No source is approved for acquisition/training.** [Machine-readable comparison](vision-dataset-assessment.json) covers ten candidates across Indian relevance, label quality, multi-food/mask support, licensing, annotation consistency, reproducibility, storage and generalization. Its qualitative assessments are not model scores. Actual archive contents/checksums remain uninspected. Public access, repository licenses and article licenses are not automatic rights to every underlying image or distributed weight.

## Indian-food audit priorities

**RASOI:** the [Food Computing Lab at Ashoka University](https://fkg-india.github.io/library/datasets/) describes standalone dish labels and composite-thali boxes, with CC BY-NC-SA 4.0 research restrictions and required attribution: “Created and maintained by the Food Computing Lab, Ashoka University, India.” Its [linked Kaggle release](https://www.kaggle.com/datasets/eda19bdde69843e6a82f85d0a6ee495139a81d5b76f79331eb54dd69e6b0d0a9) did not expose a readable card here; bounded public API search returned no matching result. Counts, bytes, exact version/access and image provenance remain unknown. Prioritize metadata/access review, not download; the name does not prove mask ground truth.

**Indian Thali Dataset:** the [IIIT Hyderabad project](https://cvit.iiit.ac.in/research/projects/cvit-projects/indian_thali) and [authors' paper](https://adityaarun1.github.io/assets/files/icvgip25/thali/Thali_ICVGIP2025_main.pdf) describe captured, multi-view plates and dense annotations. Exact release terms/access and semantic-versus-instance encoding remain unverified. All views must stay grouped by plate; institutional capture is not nationwide household coverage. The article's license is not treated as archive permission. Weight estimation is outside Phase 03.

**IndianFoodNet30:** the [original paper](https://www.iieta.org/node/16148) links the [publisher-hosted version](https://universe.roboflow.com/indianfoodnet/indianfoodnet/dataset/1), which states CC BY 4.0. The paper describes web-source collection and reviewed boxes. Hosted derived counts/splits differ from paper/original-image descriptions; require originals, source rights and augmentation lineage. Do not count three augmented outputs as three independent captures, accept existing splits without audit, or treat boxes as masks.

**Khana:** the [author site](https://khana.omkarprabhu.in/) and [preprint](https://arxiv.org/abs/2509.06006) provide a broader Indian classification candidate, while the author explicitly disclaims image copyright ownership. Research/education availability does not resolve third-party rights. Keep full data cloud-only if ever approved; verify released annotations before claiming localization capability.

**Indian80:** the [original Kaggle metadata](https://www.kaggle.com/api/v1/datasets/view/iamsouravbanerjee/indian-food-images-dataset) reports version 5 and an “Other” license with Google Images provenance. This source stays **BLOCKED** pending a usable rights basis; no mirror's CC0 claim substitutes for the publisher. No archive is acquired.

Other Indian leads were considered: [FoodLens](https://research.google/pubs/foodlens-fine-grained-and-multi-label-classification-ofindian-food-images/) reports hierarchical/multilabel research but no usable public release/license was verified here. [Datacluster's original repository](https://github.com/datacluster-labs/Indian-Food-Image-Dataset) describes mobile capture and classification/detection, but full access is sales-mediated and no dataset license was verified. Neither is an initial acquisition candidate; no sales contact, purchase or contributor-image reuse is authorized.

## General and annotation benchmarks

[Food-101's official page](https://data.vision.ee.ethz.ch/cvl/datasets_extra/food-101/) establishes a general single-dish benchmark, noisy training labels and reviewed official test labels. It is **optional pipeline/benchmark data**, not the Indian primary by default. A bounded 128 KiB in-memory HTTP Range probe of the official archive during the earlier preflight did not reach its agreement. It extracted/saved no images and did not establish training rights. No full local download is permitted.

[UECFOOD-256](https://foodcam.mobi/dataset256.html) original distribution was inaccessible during inspection; [author material](https://www.foodcam.mobi/e/pub/conf14/141106kawano_0_ppt.pdf) supports its category count. Do not invent counts/size/terms or transfer another UEC dataset's license.

[FoodSeg103](https://github.com/LARC-CMU-SMU/FoodSeg103-Benchmark-v1) is a semantic ingredient-mask candidate; resolve the base release's label/background conventions. Do not conflate the [154-class extension](https://xiongweiwu.github.io/foodseg103.html) with the base set or interpret a code license as all image rights.

[UECFoodPixComplete](https://mm.cs.uec.ac.jp/uecfoodpix/) has stated noncommercial research restrictions and manually annotated semantic masks. Verify category IDs/background/void rules from actual files. Neither it nor FoodSeg103 establishes physical instance identities, portions or Indian coverage.

[Nutrition5k](https://github.com/google-research-datasets/Nutrition5k) has clearer publisher CC BY 4.0 terms but is a large multi-view cafeteria resource with a different task. Exclude it from initial acquisition; any future use must group views by plate. Its nutrient targets are outside Phase 03.

## Coverage, quality and split acceptance

The 18 proposed concepts are a provisional review vocabulary, not a promised model head. After authorized access, review every source label/alias, annotation type and independent-group count, retain unsupported concepts explicitly, and finalize class order only when coverage is evidenced. No current source has been audited enough to establish that coverage. Single-label candidates are alternatives, not components of a mixed plate.

Preserve original files and official test membership. Group source meals/sessions, exact file/decoded hashes, reviewed near duplicates and all generated derivatives before splitting train/validation/calibration. Exclude implicated training records that overlap official test; never move test images into training. The implemented dHash grouping is a conservative candidate mechanism with dense-bucket failure, not proof of complete semantic/source deduplication. Exact duplicate conflicting labels require review. Source groups missing means no session-independence claim; class balance must be audited separately.

A small independently annotated, rights-cleared Indian/mixed/unknown challenge collection would improve domain evaluation, but collection is **not authorized or performed**. It cannot be replaced with synthetic food accuracy. Detection, semantic segmentation and instance segmentation need their own suitable annotations and measured results. No trained localization capability exists in this repository.

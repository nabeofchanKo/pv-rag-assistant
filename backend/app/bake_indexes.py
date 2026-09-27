"""Build the reference indexes (drug labels + MedDRA PTs) ahead of time.

Run at image build time (see backend/Dockerfile) so the deployed container
starts with its indexes already on disk. Without this, App Runner — which has
no persistent disk — re-embeds both corpora on every restart and deploy: a few
cents of embedding calls each time, a slower boot, and a boot-time dependency on
the embedding API being reachable.

It calls the same idempotent ``ensure_indexed`` the startup lifespan does, so a
baked image simply finds both collections populated and skips. Unlike the
lifespan, failures here are fatal: a build that silently baked an empty index
would be worse than one that stops.

    python -m app.bake_indexes
"""

import logging

from app.config import settings
from app.dependencies import get_label_index_service, get_meddra_retriever


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    labels = get_label_index_service().ensure_indexed()
    meddra = get_meddra_retriever().ensure_indexed()
    if get_label_index_service().retriever.is_empty():
        raise SystemExit("drug-label index is empty after baking")
    print(f"baked into {settings.chroma_dir}: {labels} label chunks, {meddra} MedDRA PTs")


if __name__ == "__main__":
    main()

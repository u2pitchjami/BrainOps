# from collections.abc import Sequence

# from brainops.embeddings.protocols import EmbeddingRepositoryProtocol
# from brainops.models.media import BlockPurpose, Media, MediaContext, TempBlockRef


# def build_media_embedding_context(
#     media: Media,
#     temp_block_repository: EmbeddingRepositoryProtocol,
# ) -> MediaContext:
#     """Construit le contexte des blocs d'embedding en attente d'un média."""
#     return build_media_context(
#         media,
#         temp_block_repository,
#         purpose=BlockPurpose.EMBEDDING,
#         status="processed",
#     )


# def build_media_context(
#     media: Media,
#     temp_block_repository: EmbeddingRepositoryProtocol,
#     *,
#     purpose: BlockPurpose,
#     status: str = "processed",
# ) -> MediaContext:
#     """
#     Construit le contexte de traitement d'un média.

#     Seuls les blocs correspondant au traitement demandé et au statut indiqué
#     sont intégrés au contexte.
#     """
#     blocks = temp_block_repository.get_existing_vector(
#         media_id=media.id,
#         purpose=purpose,
#         status=status,
#     )

#     block_refs: Sequence[TempBlockRef] = tuple(TempBlockRef(block_id=block.id) for block in blocks)

#     return MediaContext(
#         media=media,
#         blocks=block_refs,
#     )

def filter_dataframe(df, sample_id=None, class_id=None, biome_id=None, status=None):
    if sample_id is not None:
        df = df[df["sample_id"] == int(sample_id)]
    if class_id is not None:
        df = df[df["class_id"] == class_id]
    if biome_id is not None:
        df = df[df["biome_id"] == biome_id]
    if status is not None:
        df = df[df["status"] == status]
    return df

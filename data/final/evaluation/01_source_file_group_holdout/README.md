# Source And File-Group Holdout

`source_holdout_membership.csv.gz` contains one fold per source. For a given
`fold_id`, rows from `heldout_source` are `test`; all other rows are `train`.
This gives explicit holdout tests for every mining source and every non-mining
source.

`source_file_group_split.csv.gz` is a single train/validation/test split where
all rows from the same `(source, source_file)` group stay in the same split.
Some sources have only one source file, so those sources cannot be internally
split without violating the file-group constraint.

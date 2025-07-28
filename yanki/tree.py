from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(kw_only=True)
class TreeNode:
    name: str | None
    datum: Any | None = None
    children: dict[str, "TreeNode"] = field(default_factory=dict)

    def get_path(self, *title_path: str) -> "TreeNode":
        current = self
        for segment in title_path:
            if segment not in current.children:
                current.children[segment] = TreeNode(name=segment)
            current = current.children[segment]
        return current

    def sorted_children(self) -> list["TreeNode"]:
        return [item[1] for item in sorted(self.children.items())]


def tree(
    data: list[Any], key: Callable, *, root_name: str | None = None
) -> TreeNode:
    root = TreeNode(name=root_name)
    for datum in data:
        title_path = key(datum)
        node = root.get_path(*title_path)
        if node.datum:
            raise KeyError(
                f"two tree leaves found with same title path: {title_path!r}"
            )
        node.datum = datum

    if len(root.children) == 1:
        # If the root only has one child, return it rather than the root.
        return next(iter(root.children.values()))

    return root

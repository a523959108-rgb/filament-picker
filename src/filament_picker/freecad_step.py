"""FreeCAD console script. Run only as `freecadcmd freecad_step.py source.step dest.stl`.

This environment's Ubuntu 24.04 archive has no freecad package, so this script
was not executed against FreeCAD here. The tested converter is occt-draw.
"""

import sys

import MeshPart
import Part


def main() -> int:
    source = sys.argv[-2]
    destination = sys.argv[-1]
    shape = Part.Shape()
    shape.read(source)
    mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.1)
    mesh.write(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

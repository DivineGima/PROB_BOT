"""Team-name normalisation, alias loading and resolution (architecture section 8.5)."""

from footy.aliases.normalise import normalise
from footy.aliases.resolver import Resolver
from footy.aliases.seed import ReferenceData, TeamSeed, load_reference

__all__ = ["ReferenceData", "Resolver", "TeamSeed", "load_reference", "normalise"]

from led.Sources.SourceCLI import SourceCLI
from led.Sources.SourceFiles import SourceFiles
from led.Sources.SourceHTTP import SourceHTTP

ENABLED_SOURCES = [
    SourceCLI,
    SourceFiles,
    SourceHTTP,
]

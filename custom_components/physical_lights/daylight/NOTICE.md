# Scientific data attribution

The Python code is MIT-licensed. The following data have separate terms.

## CIE melanopic weighting data

CIE (2018), *CIE alpha-opic action spectra*, International Commission on Illumination, Vienna, Austria. [Dataset and citation](https://doi.org/10.25039/CIE.DS.vqqhzp5a).

The original CSV and metadata in `tools/data/` are reproduced unchanged under [Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/). Original CSV SHA-256: `d69ff61bd49d63f530b4fcc7be9ba2db37bf31cba1bb50a8e87c1bc86f725250`.

The `melanopic_edi` and `relative_melanopic_spread` values in `reference.json` were calculated by applying that weighting dataset to this project's modeled spectra. These derived data are also provided under CC BY-SA 4.0. They are model outputs, not measurements or CIE endorsements. The runtime reference contains the source DOI, checksum, and license in `melanopic_reference`.

The `melanopic_edi` values in `direct_reference.json` are derived from the same CIE weighting dataset and are also provided under CC BY-SA 4.0.

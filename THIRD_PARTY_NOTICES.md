# Third-Party Notices

This project can install and bundle third-party tools and rule content in the
worker image for local forensic processing. The copied license texts for the
default bundled worker components are kept under `third_party/licenses/` and
are copied into the worker image at `/licenses`.

This notice is an engineering inventory, not legal advice. Re-check upstream
terms before publishing container images or packaged builds.

## Default Worker Image

| Component | How it is included | Upstream | License / terms | Local notice files |
| --- | --- | --- | --- | --- |
| Chainsaw | Downloaded binary plus bundled rules/mappings | https://github.com/WithSecureLabs/chainsaw | GPL-3.0 | `third_party/licenses/chainsaw/LICENCE` |
| Sigma rules | Downloaded rule subset | https://github.com/SigmaHQ/sigma | Detection Rule License 1.1 for rules | `third_party/licenses/sigma/LICENSE`, `third_party/licenses/sigma/LICENSE.Detection.Rules.md` |
| Hindsight / pyhindsight | Installed from RyanDFIR/hindsight | https://github.com/RyanDFIR/hindsight | Apache-2.0 | `third_party/licenses/hindsight/LICENSE.md` |
| ccl_chromium_reader | Installed from cclgroupltd/ccl_chromium_reader | https://github.com/cclgroupltd/ccl_chromium_reader | MIT | `third_party/licenses/ccl_chromium_reader/LICENSE` |
| .NET runtime | Installed by `dotnet-install.sh` for EZ Tools | https://github.com/dotnet/runtime | MIT plus third-party notices | `third_party/licenses/dotnet-runtime/LICENSE.TXT`, `third_party/licenses/dotnet-runtime/THIRD-PARTY-NOTICES.TXT` |
| Eric Zimmerman tools: EvtxECmd, MFTECmd, RECmd, AmcacheParser, PECmd, JLECmd, LECmd | Downloaded ZIP archives into `/opt/eztools` | https://ericzimmerman.github.io/ | Upstream repositories list MIT for the bundled tools | `third_party/licenses/eztools/*-LICENSE*` |

The Sigma Detection Rule License requires attribution to rule authors,
including when displaying matches. Corvus should preserve rule metadata
such as title, author, id, and source where available in detection output.

Chainsaw is GPL-3.0. If an image or package containing Chainsaw is
redistributed, preserve its license notices and comply with GPL-3.0 source
availability obligations for Chainsaw and any modifications to it.

Eric Zimmerman tools are downloaded from the official EZ Tools distribution
site. The installed tools listed above have upstream MIT license files copied
from their public source repositories. If the default tool list changes, add
the matching upstream license file before distributing a rebuilt image.

## Optional Tools

`scripts/install-open-forensics.sh` can optionally install additional parsers.
These are not installed in the default worker image unless the matching build
arguments are enabled. If you publish an image with optional tools enabled, add
their license texts and update this notice for that image profile.

| Component | How it is included | Upstream | License / terms | Local notice files |
| --- | --- | --- | --- | --- |
| Plaso / log2timeline | pip install when `INSTALL_OPEN_FORENSICS=true` | https://github.com/log2timeline/plaso | Apache-2.0 | add before redistribution |
| mac_apt | pip install when `INSTALL_OPEN_FORENSICS=true` | https://github.com/ydkhatri/mac_apt | MIT | add before redistribution |
| Volatility 3 | pip install when `INSTALL_OPEN_FORENSICS=true` and `INSTALL_VOLATILITY3=true` | https://github.com/volatilityfoundation/volatility3 | VSL-1.0 | `third_party/licenses/volatility3/NOTICE.txt` |

Volatility 3 uses the Volatility Software License (VSL) 1.0, which is not an
OSI-approved license and has terms distinct from MIT/Apache. If you redistribute
an image that includes it, review and include the VSL-1.0 license text.

## Package Manager Dependencies

The Python, Node, Debian, Redis, and PostgreSQL dependency trees are not fully
expanded in this notice. Before public release, generate an SBOM and package
license report for the exact image and application build being distributed.

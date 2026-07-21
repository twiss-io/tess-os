# Contributor License Agreement (CLA) — Policy

This document explains **when** a Contributor License Agreement applies to work
in the Tess OS ecosystem, and **why**. It is a policy overview, not the legal
agreement itself.

## Short version

| You are contributing to… | License of your contribution | CLA required? |
|---|---|---|
| **Tess OS** (this repo — Apache-2.0) | Apache-2.0 (inbound = outbound) | **No** |
| **`twiss-io/vault`** (future standalone vault — AGPL-3.0) | AGPL-3.0 **+ CLA** | **Yes** |

## 1. Tess OS (this repository) — no CLA

Contributions to **this** repository are accepted under the project's
**Apache-2.0** license on the standard **inbound = outbound** basis: unless you
state otherwise, the work you submit is licensed to the project and its users
under the same Apache-2.0 terms the project uses (see Apache-2.0 §5 and
[CONTRIBUTING.md](CONTRIBUTING.md)).

**No separate CLA is required to contribute to Tess OS.** Opening a pull request
is your representation that you have the right to submit the work and that it is
offered under Apache-2.0. Apache-2.0 §5 already covers this; we do not ask you to
assign or relicense anything.

## 2. The future standalone vault (`twiss-io/vault`) — CLA required

A **separate, future** product — the standalone **Twiss Vault**
(`twiss-io/vault`) — is planned to be released under the **AGPL-3.0** license in
its **own repository**. That project will require a signed **Contributor License
Agreement** before contributions can be merged.

### Why a CLA there, and not here

The standalone vault is intended to be **dual-licensed**: available under AGPL-3.0
to the community, *and* available under a commercial license to organizations
that cannot or do not want to adopt AGPL terms. To offer a commercial license
legitimately, the project maintainer (Twiss) must hold sufficient rights in
**all** of the code — including contributions from others.

A CLA makes that possible. By signing it, a contributor grants Twiss the rights
needed to license their contribution under **both** AGPL-3.0 and a commercial
license, while the contributor **retains copyright** in their own work. This is
the same mechanism used by many dual-licensed open-source projects.

> Note: this Apache-2.0 repository contains **no AGPL-licensed code**. The
> standalone AGPL vault and its CLA live in a **separate** repository and do not
> change the terms of anything here. See [NOTICE](NOTICE) §3 and the
> open-core note in [README.md](README.md).

### What the CLA will (and will not) do

- It **will** ask you to grant Twiss the rights to relicense your contribution
  (so the project can be dual-licensed) and to confirm you have the right to make
  the contribution.
- It **will not** take away your copyright — you keep ownership of your work.
- It **will not** apply retroactively to your Apache-2.0 contributions in this
  repository.

## 3. Status

This is a **policy stub**. The actual CLA text, the signing process (e.g. a CLA
assistant / bot on the `twiss-io/vault` repo), and the commercial-license terms
will be published **with that repository when it opens**. No CLA is wired into
this repository, and none is needed to contribute here.

Questions: **legal@twiss.io**.

---

_This document is a plain-language summary, not the agreement itself, and is not
legal advice._

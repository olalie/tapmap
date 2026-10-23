# Third-Party Notices

This directory contains third-party software redistributed with TapMap.

---

## Microsoft.Security.Extensions

### Purpose

TapMap redistributes Microsoft.Security.Extensions to obtain Windows file
signature information.

The detailed implementation and interaction with VERSIONINFO and
WinVerifyTrust are documented in the source code.

### Version

1.4.0

### Files

- `microsoft_security_extensions/getfilesiginforedist.dll`
- `microsoft_security_extensions/getfilesiginforedistwrapper.dll`

### Copyright

© Microsoft Corporation. All rights reserved.

### License

MIT

License reference:

https://licenses.nuget.org/MIT

### Source

NuGet package:

https://www.nuget.org/packages/Microsoft.Security.Extensions

Project:

https://aka.ms/getfilesiginforedist

---

## Twemoji Country Flags

### Purpose

TapMap bundles this font to display country flag emoji consistently,
including in browsers without native flag glyphs, such as Chrome and Edge on
Windows.

### Version

`dist/TwemojiCountryFlags.woff2` from the npm package
`country-flag-emoji-polyfill` 0.1.10, redistributed unmodified.

SHA-256:
`9f04f14429bb6a9f415c7a4dd902a918d7e81a4f7526c415496fdb063954e3b8`

The same file is published in version 0.1.8.

### Files

- `src/tapmap/assets/TwemojiCountryFlags.woff2`
- `src/tapmap/assets/TwemojiCountryFlags-LICENSE.md` (upstream `LICENSE.md`)

### Origin

The font is a subset of the Twemoji Mozilla font, created by TalkJS with
`pyftsubset` from fonttools. The subset keeps only the glyphs for country
flags (regional indicator symbols) and the England, Scotland and Wales flags.

The upstream build script downloads the latest Twemoji Mozilla release at build
time. The exact source font version is not recorded upstream and has not been
confirmed.

### Copyright and license

Font subset and package: Copyright (c) 2022 TalkJS. MIT.

Emoji artwork: Copyright 2019 Twitter, Inc and other contributors. Licensed
under CC BY 4.0. Changes: subset to country flag glyphs by TalkJS.

License references:

https://creativecommons.org/licenses/by/4.0/

https://github.com/twitter/twemoji#license

### Source

npm package:

https://www.npmjs.com/package/country-flag-emoji-polyfill/v/0.1.10

Projects:

https://github.com/talkjs/country-flag-emoji-polyfill

https://github.com/mozilla/twemoji-colr

https://github.com/twitter/twemoji

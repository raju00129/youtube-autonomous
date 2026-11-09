# Autonomous weekly workflow

## Cadence (locked)

**Every day = 2 long-form songs + 4 Shorts**

| Daypart | Long-form | Shorts |
| --- | --- | --- |
| **Morning** (~06:00 IST) | 1 song (audio + looping visual) | **2 clips** cut from that same A/V (Short 2 ≈ +3h → 09:00) |
| **Evening** (~19:00 IST) | 1 song (audio + looping visual) | **2 clips** cut from that same A/V (Short 2 ≈ +2h → 21:00) |

Shorts publish at the **same daypart time** as their parent song, with a link to the main video.

Weekly volume: **14 songs · 28 Shorts**.

## Your job (admin)

1. Upload **channel logo** once (`/branding`).
2. Open **Week schedule** (`/schedule`) — each day shows Morning + Evening cards.
3. Optional title hint per daypart.
4. **Create song + 2 Shorts** per card you want to produce.

System auto-fills: weekday deity, month festive mood, Cursor lyrics, YT copy, Short stubs, and the **right YouTube playlist** (deity / morning-evening / Shorts match against channel playlist titles).

## Then (music)

5. Song Studio: approve → Suno Pro → upload **one MP3 per daypart**.

## Review & publish anytime

Open **Ready queue** (`/ready`):

- **Ready for review** — lyrics + audio done (video checklist shows until render exists)
- Set **any datetime** or click **Publish now** (mid-week / ASAP is fine)
- Shorts inherit the same publish time
- Morning/evening defaults remain on the week schedule; override per slot anytime

## System continues (next build slices)

6. Thumbnail (required): auto from lyrics mood + Pallavi + Telugu title + logo ($0)  
7. Looping visual → FFmpeg long-form  
8. Cut **2 Shorts from that same audio+video**  
9. YouTube upload worker honors queue / Publish now / custom time; inject main URL into Shorts  

## Current status

| Piece | Status |
| --- | --- |
| Morning + evening slots (2 songs / day) | Done |
| 2 Shorts per song (4 / day) | Done (stubs) |
| Auto deity / festive mood | Done |
| Logo upload | Done |
| Auto playlist pick (deity / daypart / Shorts) | Done |
| Short clip render + YouTube publish | Next |

## Playlists (auto-match)

On materialize (and via Song Studio **Re-pick playlist**), the app lists your channel playlists and picks the deity/daypart playlist (e.g. `Shiva`, `Morning Devotional`). **Shorts use that same playlist** — they are clips of the same song content (same A/V + same title/description base), not a separate Shorts playlist.

Create deity / morning / evening playlists on the channel so matches land on real IDs.

# VPS Setup (Quick)

## Paths
Everything under:
- `/opt/gpti/gpti-data-bot` (repo)
- `/opt/gpti/gpti-data-bot/data/seeds` (seed packs)

## Start
```bash
cd /opt/gpti/gpti-data-bot
chmod +x bootstrap.sh
sudo ./bootstrap.sh
```

## Seed placement
Put:
- `gpti_seed_pack_100.json`
- `gpti_seed_pack_100.csv`

into:
`/opt/gpti/gpti-data-bot/data/seeds/`

## URLs
- Prefect UI: `http://SERVER_IP:4200`
- MinIO Console: `http://SERVER_IP:9001`

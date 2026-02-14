# MinIO Object Lock Setup Guide

## Purpose
Configure MinIO for IOSCO Article 16 compliance with immutable snapshots using Write-Once-Read-Many (WORM) object lock.

## Prerequisites

1. **Install MinIO Python library:**
   ```bash
   pip install minio
   ```

2. **MinIO credentials in environment:**
   ```bash
   MINIO_ENDPOINT=localhost:9000
   MINIO_ACCESS_KEY=your_access_key
   MINIO_SECRET_KEY=your_secret_key
   ```

3. **MinIO server must support Object Lock:**
   - Available in MinIO RELEASE.2020-09-17T04-49-20Z and later
   - Docker image: `minio/minio:latest`

## Configuration Steps

### 1. Create Bucket with Object Lock

```python
from gpti_data.utils.minio_lock_config import configure_minio_for_iosco_compliance

# Configure with 90-day retention (IOSCO minimum)
results = configure_minio_for_iosco_compliance(
    retention_days=90,
    bucket_name="gpti-snapshots"
)
```

### 2. Upload Snapshots with Retention

```python
from gpti_data.utils.minio_lock_config import MinioObjectLockConfig

config = MinioObjectLockConfig(bucket_name="gpti-snapshots")

# Upload snapshot with 90-day protection
config.upload_with_retention(
    file_path="/path/to/snapshot.json",
    object_name="snapshots/2026-02-01_snapshot.json",
    retention_days=90
)
```

### 3. Verify Protection

```python
# Check object lock status
status = config.verify_object_lock("snapshots/2026-02-01_snapshot.json")
print(f"Protected: {status['protected']}")
print(f"Retain until: {status['retain_until']}")

# Test deletion protection
is_protected = config.test_deletion_protection("snapshots/2026-02-01_snapshot.json")
# Returns True if deletion is properly blocked
```

## Object Lock Modes

### Compliance Mode (Recommended for IOSCO)
- Objects **cannot be deleted** even by root user
- Retention period **cannot be shortened**
- Provides strongest protection against tampering
- Required for regulatory compliance

### Governance Mode (Alternative)
- Users with special permissions can override
- Retention can be modified by privileged users
- Not recommended for IOSCO compliance

## Retention Policies

### Bucket-Level Default
- Applied automatically to all new objects
- Configured once per bucket
- Example: 90 days retention

### Object-Level Retention
- Override bucket default for specific objects
- Set at upload time
- Example: Critical snapshots with 365-day retention

## Integration with GPTI Bot

### Modify Upload Flow

Add to `src/gpti_data/utils/storage.py`:

```python
from gpti_data.utils.minio_lock_config import MinioObjectLockConfig

class SnapshotStorage:
    def __init__(self):
        self.lock_config = MinioObjectLockConfig()
    
    def save_snapshot(self, snapshot_data, snapshot_id):
        # Save locally first
        local_path = f"/tmp/{snapshot_id}.json"
        with open(local_path, 'w') as f:
            json.dump(snapshot_data, f)
        
        # Upload with retention
        self.lock_config.upload_with_retention(
            file_path=local_path,
            object_name=f"snapshots/{snapshot_id}.json",
            retention_days=90  # IOSCO minimum
        )
```

### Prefect Flow Integration

Add to `flows/production_flow.py`:

```python
from gpti_data.utils.minio_lock_config import MinioObjectLockConfig

@flow(name="gpti-production")
def production_pipeline():
    # ... existing pipeline code ...
    
    # Upload snapshot with protection
    lock_config = MinioObjectLockConfig()
    lock_config.upload_with_retention(
        file_path=snapshot_path,
        object_name=f"snapshots/{snapshot_id}.json",
        retention_days=90
    )
    
    # Verify protection
    status = lock_config.verify_object_lock(f"snapshots/{snapshot_id}.json")
    if not status.get('protected'):
        raise Exception("Snapshot not properly protected!")
```

## Verification Checklist

- [ ] MinIO library installed (`pip install minio`)
- [ ] Bucket created with Object Lock enabled
- [ ] Default retention policy set (90+ days)
- [ ] Test upload with retention successful
- [ ] Deletion protection verified (deletion fails as expected)
- [ ] Bucket status shows `object_lock_enabled: true`
- [ ] Production flow uploads to locked bucket

## Troubleshooting

### "Bucket already exists without Object Lock"
**Problem:** Existing bucket wasn't created with Object Lock.

**Solution:** 
1. Create new bucket with different name
2. OR: Delete existing bucket and recreate with lock enabled
   ```bash
   mc rb myminio/gpti-snapshots --force
   ```

### "Object Lock not supported"
**Problem:** MinIO version too old.

**Solution:** Update MinIO to latest version:
```bash
docker pull minio/minio:latest
```

### "Permission denied"
**Problem:** Access credentials lack required permissions.

**Solution:** Ensure user has:
- `s3:PutObject`
- `s3:PutObjectRetention`
- `s3:GetObjectRetention`

## IOSCO Compliance Notes

### Article 16 Requirements Met:
- ✅ Snapshots immutable for minimum 90 days
- ✅ Cannot be altered or deleted (COMPLIANCE mode)
- ✅ Retention period enforced by MinIO
- ✅ Tamper-proof audit trail

### Documentation for Auditors:
1. Point to this setup guide
2. Show bucket Object Lock configuration
3. Demonstrate deletion protection test
4. Provide retention policy document

## Production Deployment

### 1. Update docker-compose.yml

```yaml
services:
  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    # Object Lock requires RELEASE.2020-09-17T04-49-20Z+
```

### 2. Initialize on First Deploy

```bash
cd /opt/gpti/gpti-data-bot
python3 -c "
from src.gpti_data.utils.minio_lock_config import configure_minio_for_iosco_compliance
results = configure_minio_for_iosco_compliance(retention_days=90)
print('Status:', results['status'])
"
```

### 3. Verify in Production

```bash
# Check bucket status
mc retention info myminio/gpti-snapshots

# List protected objects
mc ls --versions myminio/gpti-snapshots/
```

## References

- [MinIO Object Locking](https://min.io/docs/minio/linux/administration/object-management/object-retention.html)
- [IOSCO Article 16 - Public Disclosure](../docs/IOSCO_COMPLIANCE.md)
- [S3 Object Lock Specification](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)

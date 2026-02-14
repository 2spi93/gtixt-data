#!/usr/bin/env python3
"""
MinIO Object Lock Configuration
Created: 2026-02-01
Phase: 1 (Validation Framework) - Week 3

Purpose:
- Enable immutable snapshots (IOSCO Article 16 requirement)
- Compliance mode for write-once-read-many (WORM)
- Retention policies (minimum 90 days)
- Prevent tampering with historical data

MinIO Object Lock Features:
- Compliance Mode: Objects cannot be deleted even by root
- Retention Period: Objects protected for specified duration
- Legal Hold: Additional protection independent of retention
"""

import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Try to import MinIO
try:
    from minio import Minio
    from minio.retention import Retention, COMPLIANCE
    from minio.commonconfig import ENABLED
    MINIO_AVAILABLE = True
except ImportError:
    MINIO_AVAILABLE = False
    logger.warning("MinIO library not available - install with: pip install minio")


class MinioObjectLockConfig:
    """Configure MinIO Object Lock for immutable snapshots"""
    
    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        bucket_name: str = "gpti-snapshots"
    ):
        """
        Initialize MinIO Object Lock configuration
        
        Args:
            endpoint: MinIO endpoint (e.g., "localhost:9000")
            access_key: MinIO access key
            secret_key: MinIO secret key
            bucket_name: Bucket to configure for object lock
        """
        # Get from environment if not provided
        self.endpoint = endpoint or os.getenv("MINIO_ENDPOINT", "localhost:9000")
        self.access_key = access_key or os.getenv("MINIO_ACCESS_KEY")
        self.secret_key = secret_key or os.getenv("MINIO_SECRET_KEY")
        self.bucket_name = bucket_name
        
        # Remove http:// prefix if present
        if self.endpoint.startswith("http://"):
            self.endpoint = self.endpoint.replace("http://", "")
            self.secure = False
        elif self.endpoint.startswith("https://"):
            self.endpoint = self.endpoint.replace("https://", "")
            self.secure = True
        else:
            self.secure = False
        
        self.client = None
        
        if not MINIO_AVAILABLE:
            logger.error("MinIO library not installed")
            return
        
        if not self.access_key or not self.secret_key:
            logger.warning("MinIO credentials not provided")
            return
        
        # Initialize MinIO client
        try:
            self.client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure
            )
            logger.info(f"MinIO client initialized: {self.endpoint}")
        except Exception as e:
            logger.error(f"Failed to initialize MinIO client: {e}")
    
    def create_bucket_with_lock(self, bucket_name: Optional[str] = None) -> bool:
        """
        Create a new bucket with Object Lock enabled
        
        Args:
            bucket_name: Bucket name (uses default if not provided)
            
        Returns:
            True if successful, False otherwise
            
        Note: Object Lock must be enabled at bucket creation time
        """
        if not self.client:
            logger.error("MinIO client not initialized")
            return False
        
        bucket = bucket_name or self.bucket_name
        
        try:
            # Check if bucket already exists
            if self.client.bucket_exists(bucket):
                logger.info(f"Bucket {bucket} already exists")
                return True
            
            # Create bucket with Object Lock enabled
            self.client.make_bucket(bucket, object_lock=True)
            logger.info(f"Bucket {bucket} created with Object Lock enabled")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create bucket with Object Lock: {e}")
            return False
    
    def set_bucket_retention(
        self,
        retention_days: int = 90,
        bucket_name: Optional[str] = None
    ) -> bool:
        """
        Set default retention policy for bucket
        
        Args:
            retention_days: Number of days to retain objects (default: 90)
            bucket_name: Bucket name (uses default if not provided)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.error("MinIO client not initialized")
            return False
        
        bucket = bucket_name or self.bucket_name
        
        try:
            # Set bucket retention configuration
            from minio.objectlockconfig import ObjectLockConfig, COMPLIANCE
            
            config = ObjectLockConfig(
                mode=COMPLIANCE,
                duration_days=retention_days
            )
            
            self.client.set_object_lock_config(bucket, config)
            logger.info(f"Bucket {bucket} retention set to {retention_days} days (COMPLIANCE mode)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set bucket retention: {e}")
            return False
    
    def upload_with_retention(
        self,
        file_path: str,
        object_name: Optional[str] = None,
        retention_days: int = 90,
        bucket_name: Optional[str] = None
    ) -> bool:
        """
        Upload file with object-level retention
        
        Args:
            file_path: Path to file to upload
            object_name: Object name in MinIO (uses filename if not provided)
            retention_days: Days to retain this specific object
            bucket_name: Bucket name (uses default if not provided)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.error("MinIO client not initialized")
            return False
        
        bucket = bucket_name or self.bucket_name
        obj_name = object_name or os.path.basename(file_path)
        
        try:
            # Calculate retention until date
            retain_until = datetime.utcnow() + timedelta(days=retention_days)
            
            # Create retention configuration
            retention = Retention(
                mode=COMPLIANCE,
                retain_until_date=retain_until
            )
            
            # Upload with retention
            self.client.fput_object(
                bucket,
                obj_name,
                file_path,
                retention=retention
            )
            
            logger.info(
                f"Uploaded {obj_name} to {bucket} with {retention_days}-day retention "
                f"(protected until {retain_until.strftime('%Y-%m-%d')})"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to upload with retention: {e}")
            return False
    
    def verify_object_lock(
        self,
        object_name: str,
        bucket_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Verify Object Lock configuration for an object
        
        Args:
            object_name: Object name to check
            bucket_name: Bucket name (uses default if not provided)
            
        Returns:
            Dictionary with lock status and retention info
        """
        if not self.client:
            logger.error("MinIO client not initialized")
            return {"error": "Client not initialized"}
        
        bucket = bucket_name or self.bucket_name
        
        try:
            # Get object retention
            retention = self.client.get_object_retention(bucket, object_name)
            
            result = {
                "object": object_name,
                "bucket": bucket,
                "mode": str(retention.mode) if retention else None,
                "retain_until": retention.retain_until_date.isoformat() if retention else None,
                "protected": True if retention else False
            }
            
            logger.info(f"Object {object_name} protection verified")
            return result
            
        except Exception as e:
            logger.error(f"Failed to verify object lock: {e}")
            return {"error": str(e)}
    
    def test_deletion_protection(
        self,
        object_name: str,
        bucket_name: Optional[str] = None
    ) -> bool:
        """
        Test that protected objects cannot be deleted
        
        Args:
            object_name: Object name to test
            bucket_name: Bucket name (uses default if not provided)
            
        Returns:
            True if deletion is properly blocked, False if vulnerable
        """
        if not self.client:
            logger.error("MinIO client not initialized")
            return False
        
        bucket = bucket_name or self.bucket_name
        
        try:
            # Attempt to delete protected object
            self.client.remove_object(bucket, object_name)
            
            # If we get here, deletion succeeded - BAD!
            logger.error(f"SECURITY ISSUE: Object {object_name} was deletable despite protection!")
            return False
            
        except Exception as e:
            # Deletion blocked - GOOD!
            if "Object is WORM protected" in str(e) or "Object locked" in str(e):
                logger.info(f"✅ Deletion properly blocked for {object_name}")
                return True
            else:
                logger.warning(f"Unexpected error during deletion test: {e}")
                return False
    
    def get_bucket_status(self, bucket_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get bucket Object Lock status
        
        Args:
            bucket_name: Bucket name (uses default if not provided)
            
        Returns:
            Dictionary with bucket status
        """
        if not self.client:
            return {"error": "Client not initialized"}
        
        bucket = bucket_name or self.bucket_name
        
        try:
            # Check if bucket exists
            exists = self.client.bucket_exists(bucket)
            if not exists:
                return {"error": f"Bucket {bucket} does not exist"}
            
            # Try to get Object Lock configuration
            try:
                lock_config = self.client.get_object_lock_config(bucket)
                lock_enabled = True
                lock_mode = str(lock_config.mode) if lock_config else "N/A"
            except Exception:
                lock_enabled = False
                lock_mode = "N/A"
            
            return {
                "bucket": bucket,
                "exists": exists,
                "object_lock_enabled": lock_enabled,
                "lock_mode": lock_mode
            }
            
        except Exception as e:
            return {"error": str(e)}


def configure_minio_for_iosco_compliance(
    retention_days: int = 90,
    bucket_name: str = "gpti-snapshots"
) -> Dict[str, Any]:
    """
    Complete MinIO configuration for IOSCO compliance
    
    Args:
        retention_days: Minimum retention period (default: 90 days)
        bucket_name: Bucket name for snapshots
        
    Returns:
        Configuration status and results
    """
    config = MinioObjectLockConfig(bucket_name=bucket_name)
    
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "bucket": bucket_name,
        "retention_days": retention_days,
        "steps": []
    }
    
    if not config.client:
        results["status"] = "FAILED"
        results["error"] = "MinIO client initialization failed"
        return results
    
    # Step 1: Create bucket with Object Lock
    step1 = config.create_bucket_with_lock()
    results["steps"].append({
        "step": 1,
        "action": "Create bucket with Object Lock",
        "status": "SUCCESS" if step1 else "FAILED"
    })
    
    # Step 2: Set retention policy
    if step1:
        step2 = config.set_bucket_retention(retention_days)
        results["steps"].append({
            "step": 2,
            "action": f"Set {retention_days}-day retention policy",
            "status": "SUCCESS" if step2 else "FAILED"
        })
    
    # Step 3: Verify bucket status
    status = config.get_bucket_status()
    results["steps"].append({
        "step": 3,
        "action": "Verify bucket configuration",
        "status": "SUCCESS" if not status.get("error") else "FAILED",
        "details": status
    })
    
    results["status"] = "SUCCESS" if all(
        s["status"] == "SUCCESS" for s in results["steps"]
    ) else "PARTIAL"
    
    return results


# Example usage
if __name__ == "__main__":
    import sys
    
    print("=== MinIO Object Lock Configuration ===\n")
    
    # Configure for IOSCO compliance
    results = configure_minio_for_iosco_compliance(
        retention_days=90,
        bucket_name="gpti-snapshots"
    )
    
    print(f"Configuration Status: {results['status']}")
    print(f"Bucket: {results['bucket']}")
    print(f"Retention: {results['retention_days']} days\n")
    
    print("Steps:")
    for step in results["steps"]:
        status_emoji = "✅" if step["status"] == "SUCCESS" else "❌"
        print(f"  {status_emoji} Step {step['step']}: {step['action']}")
        if "details" in step:
            for key, value in step["details"].items():
                print(f"     - {key}: {value}")
    
    if results["status"] == "FAILED":
        print("\n⚠️  Configuration incomplete - check MinIO connection and credentials")
        sys.exit(1)
    elif results["status"] == "PARTIAL":
        print("\n⚠️  Configuration partially complete - review failed steps")
        sys.exit(1)
    else:
        print("\n✅ MinIO configured for IOSCO compliance")

# test_set_package.py - Tests for /set_package endpoint
# Run with: python3 -m pytest test_files/test_set_package.py -v

import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Create test database engine
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Patch db module BEFORE importing main
import db as db_module
db_module.engine = test_engine
db_module.SessionLocal = TestingSessionLocal

# Now import models and create tables
from models import Base, User, Package

# Import main AFTER patching db
from main import app, get_db, get_current_user

# Mock get_db to use test database
def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

# Mock authentication
def override_get_current_user():
    return {"sub": "test-user-123", "username": "testuser"}

# Apply overrides
app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_current_user] = override_get_current_user


@pytest.fixture(scope="function")
def test_client():
    """Create test client with fresh database"""
    # Recreate tables for each test
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    client = TestClient(app)
    yield client


class TestSetPackageEndpoint:
    """Test suite for /set_package endpoint"""
    
    def test_set_new_package_success(self, test_client):
        """Test setting a new package for a client"""
        response = test_client.post(
            "/set_package",
            data={
                "client_id": "CL12345678",
                "package_name": "premium"
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Package 'premium' set for client CL12345678"
        assert data["package"]["client_id"] == "CL12345678"
        assert data["package"]["package_name"] == "premium"
        assert data["package"]["previous_package"] == "premium"
        assert data["package"]["started_with"] == "premium"
        
    def test_update_existing_package(self, test_client):
        """Test updating an existing package"""
        # First create a package
        test_client.post(
            "/set_package",
            data={
                "client_id": "CL87654321",
                "package_name": "basic"
            }
        )
        
        # Update the package
        response = test_client.post(
            "/set_package",
            data={
                "client_id": "CL87654321",
                "package_name": "enterprise"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Package updated to 'enterprise' for client CL87654321"
        assert data["package"]["package_name"] == "enterprise"
        assert data["package"]["previous_package"] == "basic"
        assert data["package"]["started_with"] == "basic"
        
    def test_package_downgrade(self, test_client):
        """Test downgrading a package"""
        # Create premium package first
        test_client.post(
            "/set_package",
            data={
                "client_id": "CL99999999",
                "package_name": "premium"
            }
        )
        
        # Downgrade to basic
        response = test_client.post(
            "/set_package",
            data={
                "client_id": "CL99999999",
                "package_name": "basic"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["package"]["package_name"] == "basic"
        assert data["package"]["previous_package"] == "premium"
        
    def test_multiple_packages_same_session(self, test_client):
        """Test handling multiple different clients"""
        clients = [
            ("CL11111111", "starter"),
            ("CL22222222", "basic"),
            ("CL33333333", "premium"),
        ]
        
        for client_id, package in clients:
            response = test_client.post(
                "/set_package",
                data={
                    "client_id": client_id,
                    "package_name": package
                }
            )
            assert response.status_code == 201
            data = response.json()
            assert data["package"]["client_id"] == client_id
            assert data["package"]["package_name"] == package
            
    def test_package_name_with_special_chars(self, test_client):
        """Test package names with special characters"""
        response = test_client.post(
            "/set_package",
            data={
                "client_id": "CL44444444",
                "package_name": "enterprise-plus_v2.0"
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["package"]["package_name"] == "enterprise-plus_v2.0"
        
    def test_missing_client_id(self, test_client):
        """Test request without client_id"""
        response = test_client.post(
            "/set_package",
            data={
                "package_name": "premium"
            }
        )
        
        assert response.status_code == 422
        
    def test_missing_package_name(self, test_client):
        """Test request without package_name"""
        response = test_client.post(
            "/set_package",
            data={
                "client_id": "CL66666666"
            }
        )
        
        assert response.status_code == 422


class TestGetPackageEndpoint:
    """Test suite for /packages/{client_id} endpoint"""
    
    def test_get_existing_package(self, test_client):
        """Test retrieving an existing package"""
        # Create package first
        test_client.post(
            "/set_package",
            data={
                "client_id": "CL77777777",
                "package_name": "professional"
            }
        )
        
        # Get the package
        response = test_client.get("/packages/CL77777777")
        
        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Package retreived successfully for client CL77777777"
        assert data["package"]["client_id"] == "CL77777777"
        assert data["package"]["package_name"] == "professional"
        
    def test_get_nonexistent_package(self, test_client):
        """Test retrieving a package that doesn't exist"""
        response = test_client.get("/packages/CLNONEXISTENT")
        
        assert response.status_code == 404
        # The endpoint returns a plain string, not JSON
        assert response.text == "\"Package not found\""
        assert "Package not found" in response.text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

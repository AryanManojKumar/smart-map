from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
import requests
from backend.config import AUTH0_DOMAIN, AUTH0_AUDIENCE
from functools import lru_cache

security = HTTPBearer()

@lru_cache()
def get_jwks():
    """Get Auth0 public keys for JWT verification."""
    url = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"
    response = requests.get(url)
    return response.json()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify Auth0 JWT token and return user info."""
    token = credentials.credentials
    
    try:
        # Get signing key
        jwks = get_jwks()
        unverified_header = jwt.get_unverified_header(token)
        
        # Debug logging
        print(f"[Auth Debug] Token header: {unverified_header}")
        
        # Decode without verification to see the payload
        unverified_payload = jwt.get_unverified_claims(token)
        print(f"[Auth Debug] Token audience: {unverified_payload.get('aud')}")
        print(f"[Auth Debug] Expected audience: {AUTH0_AUDIENCE}")
        
        rsa_key = {}
        for key in jwks["keys"]:
            if key["kid"] == unverified_header["kid"]:
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"]
                }
        
        if not rsa_key:
            print(f"[Auth Debug] No matching key found for kid: {unverified_header.get('kid')}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to find appropriate key"
            )
        
        # Verify token - handle multiple audiences
        try:
            # Decode without verification first to check audience
            unverified_payload = jwt.get_unverified_claims(token)
            token_audiences = unverified_payload.get('aud', [])
            
            # Debug logging
            print(f"[Auth Debug] Token audience: {token_audiences}")
            print(f"[Auth Debug] Expected audience: {AUTH0_AUDIENCE}")
            
            # Check if our audience is in the token's audience list
            if isinstance(token_audiences, list):
                if AUTH0_AUDIENCE not in token_audiences:
                    print(f"[Auth Debug] Token verification failed: Invalid audience")
                    raise JWTError("Invalid audience")
            else:
                if token_audiences != AUTH0_AUDIENCE:
                    print(f"[Auth Debug] Token verification failed: Invalid audience")
                    raise JWTError("Invalid audience")
            
            # Now verify with proper audience handling
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=["RS256"],
                issuer=f"https://{AUTH0_DOMAIN}/",
                options={"verify_aud": False}  # We already verified audience above
            )
            print(f"[Auth Debug] Token verified successfully. User: {payload.get('sub')}")
        except JWTError as e:
            print(f"[Auth Debug] Token verification failed: {str(e)}")
            raise
        
        return payload
        
    except JWTError as e:
        print(f"[Auth Error] JWT Error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )
    except Exception as e:
        print(f"[Auth Error] Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}"
        )

def get_current_user(token_payload: dict = Depends(verify_token)):
    """Extract user info from verified token."""
    return {
        "user_id": token_payload.get("sub"),
        "email": token_payload.get("email"),
        "name": token_payload.get("name")
    }

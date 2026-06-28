import asyncio
import time
import httpx
import uuid

async def main():
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    password = "password123"
    url = "http://bpi3gp9ifi21isq0sy79is6k.152.42.188.239.sslip.io"
    
    async with httpx.AsyncClient() as client:
        # Register
        print("Registering...")
        r = await client.post(f"{url}/api/auth/register", json={"email": email, "password": password})
        if r.status_code != 201:
            print("Register failed:", r.text)
            return
            
        # Login
        print("Logging in...")
        l = await client.post(f"{url}/api/auth/login", json={"email": email, "password": password})
        token = l.json()["access_token"]
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test stats
        print("Testing stats...")
        t0 = time.time()
        s = await client.get(f"{url}/api/stats", headers=headers)
        t1 = time.time()
        print(f"Stats time: {t1-t0:.4f}s")
        print(f"Stats status: {s.status_code}")

        # Test projects
        print("Testing projects...")
        t0 = time.time()
        p = await client.get(f"{url}/api/projects", headers=headers)
        t1 = time.time()
        print(f"Projects time: {t1-t0:.4f}s")

if __name__ == "__main__":
    asyncio.run(main())

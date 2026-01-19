from fastapi import Depends, FastAPI

from src.core.dependencies import get_db
from src.users.router import users

app = FastAPI(
    title="Oja Backend",
    description="Oja Backend API",
    version="0.1.0",
    contact={
        "name": "Oja Backend Team",
        "email": "biteatertest+oja-backend@gmail.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
)

# Register routes
# User routes
app.include_router(users, dependencies=[Depends(get_db)])


@app.get("/health")
async def health_check():
    return {"status": "ok"}

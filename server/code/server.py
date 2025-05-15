from fastapi import FastAPI, Depends
from endpoints import anchors, users, files, dashboard, admin, dbsync
from auth.session import AuthMiddleware, get_current_user, require_group
from code.core.ancdb import ancDB



app = FastAPI()
app.add_middleware(AuthMiddleware)

# Carga de endpoints principales
app.include_router(anchors.router, prefix="/anchors")
app.include_router(files.router, prefix="/files")
app.include_router(dashboard.router)
app.include_router(users.router) 
app.include_router(dbsync.router)

# PHealt
@app.get("/health")
def health():
    db = ancDB()
    if db.test_connection():
        return {"status": "ok"}
    else:
        return {"status": "error", "message": "Database connection failed"}








'''
@app.get("/private")
def private_endpoint(user: str = Depends(get_current_user)):
    return {"message": f"Hola {user}, estás autenticado."}


@app.get("/admin")
def admin_endpoint(
    user: str = Depends(get_current_user),
    _=Depends(require_group("devops"))
):
    return {"message": f"Bienvenido {user}, tienes acceso DevOps"}
'''


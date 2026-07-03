import sqlite3
import json

def ver_base_de_datos():
    conn = sqlite3.connect("agencia.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT user_id, estado, historial FROM conversaciones")
    filas = cursor.fetchall()
    
    print("\n" + "="*50)
    print("📊 ESTADO ACTUAL DE LA BASE DE DATOS")
    print("="*50)
    
    if not filas:
        print("La base de datos está vacía.")
    
    for fila in filas:
        user_id = fila[0]
        estado = fila[1]
        historial = json.loads(fila[2])
        
        print(f"\n👤 USUARIO ID: {user_id}")
        print(f"📍 FASE DEL EMBUDO: {estado}")
        print(f"💬 MENSAJES GUARDADOS: {len(historial)}")
        
        # Mostramos los últimos 3 mensajes para cotillear
        print("Últimos mensajes:")
        for msg in historial[-3:]:
            rol = msg.get("role", "desconocido")
            # Si es una tool call o resultado de tool, lo mostramos resumido
            if rol == "tool":
                print(f"   ⚙️ [TOOL]: {msg.get('content')[:50]}...")
            elif "tool_calls" in msg:
                print(f"   🤖 [IA USÓ HERRAMIENTA]: {msg['tool_calls'][0]['function']['name']}")
            else:
                texto = msg.get("content", "")
                if texto:
                    print(f"   {'🧑 Tú' if rol == 'user' else '🤖 IA'}: {texto[:60]}...")
    
    print("\n" + "="*50)
    conn.close()

if __name__ == "__main__":
    ver_base_de_datos()
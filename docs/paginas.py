import subprocess,json,sys
pdf=sys.argv[1]
heads=["1. Introducción y objetivos","2. Restricciones","3. Alcance y contexto del sistema","4. Estrategia de solución","5. Vista de bloques de construcción","5.2 Nivel 2 — contenedores","5.3 Nivel 3 — componentes del microservicio de IA","6. Vista de ejecución","7. Vista de implementación","7.1 Despliegue actual y objetivo","7.2 Dimensionamiento de recursos","7.3 Estimación de costos","7.4 Pipeline y gitflow","8. Conceptos transversales","8.1 Observabilidad","8.2 Confiabilidad y alta disponibilidad","8.3 Seguridad y datos personales","8.4 Datos: tratamiento, variables y modelo de datos","9. Decisiones de arquitectura","10. Requisitos de calidad","Anexo A. Referencias","Anexo B. Declaración de uso de IA generativa","Anexo C. Repositorios y sistema"]
n=int([l for l in subprocess.run(["pdfinfo",pdf],capture_output=True,text=True).stdout.splitlines() if l.startswith("Pages")][0].split()[1])
res={"Historial de versiones":2}
for p in range(3,n+1):
    t=subprocess.run(["pdftotext","-f",str(p),"-l",str(p),pdf,"-"],capture_output=True,text=True).stdout
    for h in heads:
        if h not in res and any(l.strip().startswith(h) for l in t.splitlines()): res[h]=p
json.dump(res,open("paginas.json","w"),ensure_ascii=False); print(res)

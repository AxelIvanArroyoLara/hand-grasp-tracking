# Auditoría de seguridad

El repositorio ya tenía un remoto configurado para el proyecto. La inspección se limitó al directorio académico y a herramientas instaladas. Se usaron las publicaciones y repositorios oficiales como documentación. El modelo de Google se fija por versión y se verifica con SHA-256. DexYCB se mantiene fuera de Git. Los archivos de anotaciones NumPy se abren con pickle desactivado.

El acceso de red se limitó a documentación y recursos oficiales, dependencias públicas,
el modelo de Google y el remoto Git del proyecto. Los archivos parciales de DexYCB se
mantuvieron en el área ignorada. Se inspeccionó la estructura de cada TAR antes
de escribir sus archivos. El ZIP usa una lista explícita para excluir datos, entornos,
pesos y archivos personales. No se registraron instrucciones externas sospechosas.

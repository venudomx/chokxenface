function initSolarSystem() {
    const container = document.querySelector('.video-bg');
    if (!container) return;

    const iframe = container.querySelector('iframe');
    if (iframe) iframe.remove();

    const canvas = document.createElement('canvas');
    canvas.style.position = 'absolute';
    canvas.style.top = '0';
    canvas.style.left = '0';
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    canvas.style.zIndex = '-4';
    container.appendChild(canvas);

    const ctx = canvas.getContext('2d');
    let width, height;

    function resize() {
        width = window.innerWidth;
        height = window.innerHeight;
        canvas.width = width;
        canvas.height = height;
    }
    window.addEventListener('resize', resize);
    resize();

    const speedMultiplier = 0.008;

    const planets = [
        { name: "Mercurio", dist: 50, size: 2.5, color: "#9e9e9e", type: "solid", speed: (365 / 88) * speedMultiplier },
        { name: "Venus",    dist: 75, size: 4.5, color: "#e3bb75", type: "atmos", atmosColor: "rgba(227, 187, 117, 0.4)", speed: (365 / 225) * speedMultiplier },
        { name: "Tierra",   dist: 110, size: 5.5, color: "#2B82C9", type: "earth", atmosColor: "rgba(100, 180, 255, 0.5)", speed: 1.0 * speedMultiplier },
        { name: "Marte",    dist: 145, size: 3.5, color: "#c1440e", type: "solid", speed: (365 / 687) * speedMultiplier },
        { name: "Júpiter",  dist: 230, size: 16, color: "#c88b3a", type: "gas", bands: ["#d39c7e", "#c88b3a", "#a56026", "#d39c7e", "#e3d5a4", "#c88b3a"], speed: (1 / 11.8) * speedMultiplier },
        { name: "Saturno",  dist: 330, size: 13, color: "#e3d5a4", type: "gas", bands: ["#e3d5a4", "#cba135", "#e3d5a4", "#a88b45", "#e3d5a4"], speed: (1 / 29.4) * speedMultiplier, ring: true },
        { name: "Urano",    dist: 410, size: 9.0, color: "#4b70dd", type: "atmos", atmosColor: "rgba(75, 112, 221, 0.5)", speed: (1 / 84) * speedMultiplier },
        { name: "Neptuno",  dist: 490, size: 8.5, color: "#274687", type: "atmos", atmosColor: "rgba(39, 70, 135, 0.5)", speed: (1 / 164) * speedMultiplier }
    ];

    planets.forEach(p => p.angle = Math.random() * Math.PI * 2);

    const asteroids = [];
    for(let i = 0; i < 1500; i++) {
        let isKuiper = Math.random() > 0.5;
        let d = isKuiper ? 510 + (Math.random() * 200) : 160 + (Math.random() * 50);
        let orbitalSpeed = isKuiper ? ((1 / 200) * speedMultiplier) : ((1 / 4) * speedMultiplier);
        
        asteroids.push({
            dist: d,
            angle: Math.random() * Math.PI * 2,
            speed: orbitalSpeed * (Math.random() * 0.5 + 0.5),
            size: Math.random() * 1.2,
            color: `rgba(200,200,200,${Math.random() * 0.5 + 0.1})`
        });
    }

    const stars = [];
    for(let i = 0; i < 800; i++) {
        stars.push({
            x: Math.random() * window.innerWidth,
            y: Math.random() * window.innerHeight,
            size: Math.random() * 1.5,
            alpha: Math.random() * 0.8 + 0.1,
            twinkleSpeed: Math.random() * 0.05
        });
    }

    const tilt = 0.5; // Vista isométrica 3D

    let time = 0;

    function draw() {
        time += 1;
        
        // Deep space background with subtle radial gradient
        const bgGrad = ctx.createRadialGradient(width/2, height/2, 0, width/2, height/2, width);
        bgGrad.addColorStop(0, '#0a0a1a'); // very dark blue center
        bgGrad.addColorStop(1, '#020205'); // absolute black edges
        ctx.fillStyle = bgGrad;
        ctx.fillRect(0, 0, width, height);

        const cx = width / 2;
        const cy = height / 2;
        
        const scale = Math.max(0.5, Math.min(width, height) / 1000) * 1.2;

        // Background Stars (with twinkle)
        stars.forEach(s => {
            let currentAlpha = s.alpha + Math.sin(time * s.twinkleSpeed) * 0.2;
            ctx.fillStyle = `rgba(255,255,255,${currentAlpha})`;
            ctx.beginPath();
            ctx.arc(s.x, s.y, s.size, 0, Math.PI*2);
            ctx.fill();
        });

        // Milky Way dust effect
        ctx.save();
        ctx.translate(cx, cy);
        
        // Transform the entire solar system
        ctx.scale(scale, scale * tilt);

        // Órbitas reales
        ctx.lineWidth = 0.3;
        planets.forEach(p => {
            ctx.beginPath();
            ctx.arc(0, 0, p.dist, 0, Math.PI * 2);
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
            ctx.stroke();
        });

        // Asteroids
        asteroids.forEach(a => {
            a.angle += a.speed;
            const ax = Math.cos(a.angle) * a.dist;
            const ay = Math.sin(a.angle) * a.dist;
            ctx.fillStyle = a.color;
            ctx.beginPath();
            ctx.arc(ax, ay, a.size / scale, 0, Math.PI * 2);
            ctx.fill();
        });

        // ESTRELLA (EL SOL) - Efecto realista multicapa
        // 1. Corona inmensa brillante
        let sunGlow = ctx.createRadialGradient(0, 0, 15, 0, 0, 80);
        sunGlow.addColorStop(0, 'rgba(255, 255, 255, 1)');
        sunGlow.addColorStop(0.2, 'rgba(255, 230, 100, 0.8)');
        sunGlow.addColorStop(0.5, 'rgba(255, 120, 0, 0.3)');
        sunGlow.addColorStop(1, 'rgba(255, 50, 0, 0)');
        ctx.fillStyle = sunGlow;
        ctx.beginPath();
        ctx.arc(0, 0, 80, 0, Math.PI * 2);
        ctx.fill();

        // 2. Superficie incandescente
        ctx.beginPath();
        ctx.arc(0, 0, 24, 0, Math.PI * 2);
        ctx.fillStyle = '#ffcc00';
        ctx.fill();

        // PLANETAS
        planets.forEach(p => {
            p.angle -= p.speed;
            const px = Math.cos(p.angle) * p.dist;
            const py = Math.sin(p.angle) * p.dist;

            ctx.save();
            ctx.translate(px, py);
            
            // Undo the parent tilt just for drawing the sphere so it stays round, 
            // but keep the scale. To keep them perfectly round despite the system's tilt:
            ctx.scale(1, 1/tilt);

            // Anillos de saturno (Drawn behind the planet if technically in back, but we just draw it mostly)
            if(p.ring) {
                ctx.beginPath();
                // To keep ring tilted, we apply tilt again
                ctx.scale(1, tilt);
                ctx.ellipse(0, 0, p.size * 2.5, p.size * 0.8, -0.3, 0, Math.PI * 2);
                
                let ringGrad = ctx.createRadialGradient(0,0, p.size*1.2, 0,0, p.size*2.5);
                ringGrad.addColorStop(0, 'rgba(229, 211, 154, 0)');
                ringGrad.addColorStop(0.5, 'rgba(229, 211, 154, 0.8)');
                ringGrad.addColorStop(0.8, 'rgba(180, 150, 100, 0.6)');
                ringGrad.addColorStop(1, 'rgba(229, 211, 154, 0)');
                
                ctx.strokeStyle = ringGrad;
                ctx.lineWidth = 4;
                ctx.stroke();
                ctx.scale(1, 1/tilt); // undo ring tilt
            }

            // Create planet clip area (round)
            ctx.beginPath();
            ctx.arc(0, 0, p.size, 0, Math.PI * 2);
            ctx.clip(); // Only draw inside the planet circle

            // DIBUJAR SUPERFICIE REALISTA SEGÚN TIPO
            if (p.type === "gas") {
                // Júpiter/Saturno -> Bandas de gas horizontales
                const bandGrad = ctx.createLinearGradient(0, -p.size, 0, p.size);
                p.bands.forEach((color, idx) => {
                    bandGrad.addColorStop(idx / (p.bands.length - 1), color);
                });
                ctx.fillStyle = bandGrad;
                ctx.fillRect(-p.size, -p.size, p.size*2, p.size*2);
            } 
            else if (p.type === "earth") {
                // Océano
                ctx.fillStyle = p.color;
                ctx.fillRect(-p.size, -p.size, p.size*2, p.size*2);
                // Continentes verdes falsos usando un par de círculos
                ctx.fillStyle = '#6ab04c';
                ctx.beginPath(); ctx.arc(-p.size*0.2, -p.size*0.3, p.size*0.6, 0, Math.PI*2); ctx.fill();
                ctx.beginPath(); ctx.arc(p.size*0.4, p.size*0.2, p.size*0.5, 0, Math.PI*2); ctx.fill();
                // Nubes blancas falsas
                ctx.fillStyle = 'rgba(255,255,255,0.7)';
                ctx.beginPath(); ctx.arc(0, -p.size*0.6, p.size*0.4, 0, Math.PI*2); ctx.fill();
                ctx.beginPath(); ctx.arc(-p.size*0.4, p.size*0.5, p.size*0.3, 0, Math.PI*2); ctx.fill();
            } 
            else {
                // Planetas rocosos o de hielo lisos
                ctx.fillStyle = p.color;
                ctx.fillRect(-p.size, -p.size, p.size*2, p.size*2);
            }

            // ILUMINACIÓN REALISTA (SOMBRA 3D)
            // Calculamos el ángulo desde el Sol (0,0) hasta el Planeta (px, py)
            const angleToSun = Math.atan2(py, px);
            
            // Creamos un gradiente radial desplazado hacia la dirección del sol
            // El brillo estará en (-cos(angle), -sin(angle)) relativo al centro del planeta
            const highlightX = -Math.cos(angleToSun) * (p.size * 0.6);
            const highlightY = -Math.sin(angleToSun) * (p.size * 0.6);
            
            const lightGrad = ctx.createRadialGradient(highlightX, highlightY, 0, 0, 0, p.size);
            lightGrad.addColorStop(0, 'rgba(255, 255, 255, 0.4)'); // Brillo especular
            lightGrad.addColorStop(0.3, 'rgba(255, 255, 255, 0)');
            lightGrad.addColorStop(0.7, 'rgba(0, 0, 0, 0.6)');     // Terminador de sombra
            lightGrad.addColorStop(1, 'rgba(0, 0, 0, 0.95)');      // Lado oscuro absoluto
            
            ctx.fillStyle = lightGrad;
            ctx.beginPath();
            ctx.arc(0, 0, p.size+1, 0, Math.PI * 2);
            ctx.fill();

            // Quitamos el clip paramétrico
            ctx.restore(); // restoring from previous save (which had clip active)

            // DIBUJAR ATMÓSFERA EXTERIOR (Fuera del cuerpo sólido)
            ctx.save();
            ctx.translate(px, py);
            ctx.scale(1, 1/tilt);
            if (p.atmosColor) {
                const atmosGrad = ctx.createRadialGradient(0, 0, p.size, 0, 0, p.size * 1.4);
                atmosGrad.addColorStop(0, p.atmosColor);
                atmosGrad.addColorStop(1, 'rgba(0,0,0,0)');
                ctx.fillStyle = atmosGrad;
                ctx.beginPath();
                ctx.arc(0, 0, p.size * 1.4, 0, Math.PI*2);
                ctx.fill();
            }
            ctx.restore();
        });

        ctx.restore(); // Restore global translation and scaling
        requestAnimationFrame(draw);
    }
    
    draw();
}

document.addEventListener('DOMContentLoaded', initSolarSystem);

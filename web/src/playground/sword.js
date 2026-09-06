// web/src/playground/sword.js
// Phase 5: a simple 3D sword whose orientation follows the Motion Engine's
// quaternion, with a slash trail that flares on SLASH_* gestures. Purpose is to
// verify IMU -> orientation -> motion -> gesture end to end; visual quality is
// explicitly not graded (GOAL.md §5).

import * as THREE from "three";
import { qConjugate, qRotate } from "../motion/quaternion.js";

export class SwordScene {
  constructor(canvas) {
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: true,
      preserveDrawingBuffer: true, // lets the canvas be screenshotted / pixel-read
    });
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0a0d13);

    this.camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
    this.camera.position.set(0, 1.1, 4.2);
    this.camera.lookAt(0, 0.4, 0);

    this.scene.add(new THREE.HemisphereLight(0xbcd8ff, 0x1a1f2b, 1.1));
    const key = new THREE.DirectionalLight(0xffffff, 1.4);
    key.position.set(3, 5, 4);
    this.scene.add(key);

    // ground grid for spatial reference
    const grid = new THREE.GridHelper(10, 20, 0x2b3446, 0x1b2130);
    grid.position.y = -1.2;
    this.scene.add(grid);

    this.sword = this._buildSword();
    this.scene.add(this.sword);

    // slash trail
    this.trailMat = new THREE.MeshBasicMaterial({
      color: 0x4fd6be,
      transparent: true,
      opacity: 0,
      side: THREE.DoubleSide,
    });
    this.trail = new THREE.Mesh(new THREE.PlaneGeometry(2.2, 0.5), this.trailMat);
    this.trail.position.set(0, 0.4, 0);
    this.scene.add(this.trail);
    this._trailUntil = 0;

    this._q = [1, 0, 0, 0];
    this._resize();
    window.addEventListener("resize", () => this._resize());
  }

  _buildSword() {
    const g = new THREE.Group();
    const steel = new THREE.MeshStandardMaterial({ color: 0xd7dee8, metalness: 0.9, roughness: 0.25 });
    const gold = new THREE.MeshStandardMaterial({ color: 0xcaa04a, metalness: 0.8, roughness: 0.35 });
    const grip = new THREE.MeshStandardMaterial({ color: 0x5a3b28, metalness: 0.1, roughness: 0.8 });

    const blade = new THREE.Mesh(new THREE.BoxGeometry(0.09, 2.0, 0.02), steel);
    blade.position.y = 1.1;
    // bevel the tip
    const tip = new THREE.Mesh(new THREE.ConeGeometry(0.065, 0.22, 4), steel);
    tip.position.y = 2.2;
    tip.rotation.y = Math.PI / 4;

    const guard = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.09, 0.09), gold);
    guard.position.y = 0.05;
    const handle = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.42, 16), grip);
    handle.position.y = -0.2;
    const pommel = new THREE.Mesh(new THREE.SphereGeometry(0.075, 16, 16), gold);
    pommel.position.y = -0.44;

    g.add(blade, tip, guard, handle, pommel);
    g.position.y = 0.1;
    return g;
  }

  _resize() {
    const c = this.renderer.domElement;
    const w = c.clientWidth || 640;
    const h = c.clientHeight || 380;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  /** @param {object} state MotionState */
  update(state, now = performance.now() / 1000) {
    const [w, x, y, z] = state.orientation.quaternion;
    // three.js quaternion is (x, y, z, w)
    this.sword.quaternion.set(x, y, z, w);

    if (state.gesture && state.gesture.gesture.startsWith("SLASH")) {
      const g = state.gesture;
      // orient the trail plane along the world-space swing direction
      const worldDir = qRotate([w, x, y, z], g.direction); // body -> world
      const angle = Math.atan2(worldDir[1], worldDir[0]);
      this.trail.rotation.z = angle + Math.PI / 2;
      this.trailMat.opacity = 0.55 * (0.4 + 0.6 * g.strength);
      this._trailUntil = now + 0.18;
    }
    if (now > this._trailUntil && this.trailMat.opacity > 0) {
      this.trailMat.opacity = Math.max(0, this.trailMat.opacity - 0.06);
    }
    void qConjugate;
  }

  render() {
    this.renderer.render(this.scene, this.camera);
  }
}

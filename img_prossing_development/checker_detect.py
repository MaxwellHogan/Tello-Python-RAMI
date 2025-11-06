import cv2
import numpy as np

# --- Parameters ---
CHECKERBOARD = (15, 10)
PATCH_RADIUS = 5  # size of the local patch around corners for refinement

# --- Load image ---
image = cv2.imread("checkerboard.jpg")
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

# --- Step 1: Detect coarse corners ---
found, corners = cv2.findChessboardCorners(gray, CHECKERBOARD, None)

if found:
    for i, c in enumerate(corners):
        x, y = c.ravel()

        # --- Step 2: Extract a local patch around the corner ---
        x, y = int(x), int(y)
        patch = gray[y - PATCH_RADIUS:y + PATCH_RADIUS + 1,
                     x - PATCH_RADIUS:x + PATCH_RADIUS + 1]

        if patch.shape[0] == 0 or patch.shape[1] == 0:
            continue  # skip if corner near image edge

        # --- Step 3: Compute image gradients in x and y directions ---
        gx = cv2.Sobel(patch, cv2.CV_64F, 1, 0, ksize=3)
        gy = cv2.Sobel(patch, cv2.CV_64F, 0, 1, ksize=3)

        # --- Step 4: Compute corner strength map (like Harris) ---
        Ixx = gx * gx
        Iyy = gy * gy
        Ixy = gx * gy

        # Average over patch
        Sxx = Ixx.sum()
        Syy = Iyy.sum()
        Sxy = Ixy.sum()

        # --- Step 5: Estimate subpixel shift by center of mass of gradients ---
        # This is a simplified visual method for teaching
        weight = np.abs(gx) + np.abs(gy)
        ys, xs = np.mgrid[0:patch.shape[0], 0:patch.shape[1]]
        if weight.sum() > 0:
            cx = (xs * weight).sum() / weight.sum()
            cy = (ys * weight).sum() / weight.sum()
        else:
            cx, cy = PATCH_RADIUS, PATCH_RADIUS

        refined_x = x + (cx - PATCH_RADIUS)
        refined_y = y + (cy - PATCH_RADIUS)

        # --- Draw visualization ---
        cv2.circle(image, (x, y), 3, (0, 255, 0), 1)   # coarse corner (green)
        cv2.circle(image, (int(refined_x), int(refined_y)), 3, (0, 0, 255), -1)  # refined (red)

        # Optional: show local patch with gradient visualization
        # cv2.imshow(f"patch_{i}", cv2.convertScaleAbs(gx) + cv2.convertScaleAbs(gy))

    cv2.imshow("Checkerboard Corners - Coarse (green) and Refined (red)", image)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

else:
    print("Checkerboard not found.")

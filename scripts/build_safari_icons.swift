// Draw original shield artwork; no external image or font assets.
import AppKit

let directory = URL(fileURLWithPath: "safari/extension/images", isDirectory: true)
try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
for size in [16, 19, 32, 38, 48, 64, 96, 128, 256, 512] {
    let bitmap = NSBitmapImageRep(
        bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size,
        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
        isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0
    )!
    NSGraphicsContext.saveGraphicsState()
    let context = NSGraphicsContext(bitmapImageRep: bitmap)!
    NSGraphicsContext.current = context
    let cg = context.cgContext
    cg.scaleBy(x: CGFloat(size) / 64, y: CGFloat(size) / 64)
    cg.setFillColor((size <= 38 ? NSColor.black : NSColor(
        srgbRed: 0.12, green: 0.29, blue: 0.52, alpha: 1
    )).cgColor)
    cg.move(to: CGPoint(x: 32, y: 60))
    cg.addLine(to: CGPoint(x: 56, y: 50))
    cg.addCurve(to: CGPoint(x: 32, y: 4),
                control1: CGPoint(x: 56, y: 24), control2: CGPoint(x: 49, y: 14))
    cg.addCurve(to: CGPoint(x: 8, y: 50),
                control1: CGPoint(x: 15, y: 14), control2: CGPoint(x: 8, y: 24))
    cg.closePath()
    cg.fillPath()
    cg.setBlendMode(.clear)
    cg.fill(CGRect(x: 29, y: 28, width: 6, height: 20))
    cg.fillEllipse(in: CGRect(x: 29, y: 17, width: 6, height: 6))
    NSGraphicsContext.restoreGraphicsState()
    let data = bitmap.representation(using: .png, properties: [:])!
    try data.write(to: directory.appendingPathComponent("icon-\(size).png"), options: .atomic)
}

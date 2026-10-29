# Maintainer: Jason Persinger <jason.persinger@gmail.com>
pkgname=pgpgoblin
pkgver=1.1.0
pkgrel=1
pkgdesc="Minimalist PGP notepad/scratchpad interfacing directly with native system GnuPG"
arch=('any')
url="https://github.com/jasonpersinger/PGPGOBLIN"
license=('MIT')
depends=('gnupg' 'pinentry' 'python' 'python-gnupg' 'python-pyqt6')
optdepends=('python-pyqt5: Qt5 backend fallback')
source=("pgpgoblin.py"
        "pgpgoblin.desktop"
        "pgpgoblin.svg"
        "pgpgoblin_icon.png")
sha256sums=('SKIP'
            'SKIP'
            'SKIP'
            'SKIP')

package() {
    install -Dm755 "${srcdir}/pgpgoblin.py" "${pkgdir}/usr/bin/pgpgoblin"
    install -Dm644 "${srcdir}/pgpgoblin.desktop" "${pkgdir}/usr/share/applications/pgpgoblin.desktop"
    install -Dm644 "${srcdir}/pgpgoblin.svg" "${pkgdir}/usr/share/icons/hicolor/scalable/apps/pgpgoblin.svg"
    install -Dm644 "${srcdir}/pgpgoblin_icon.png" "${pkgdir}/usr/share/icons/hicolor/512x512/apps/pgpgoblin.png"
}

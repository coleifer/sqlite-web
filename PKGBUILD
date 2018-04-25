# Maintainer: Shreyansh Khajanchi <shreyansh_k@live.com>

pkgname=('python-sqlite-web')
pkgver=0.1.8
pkgrel=0
pkgdesc='Web-based SQLite database browser written in Python'
url='https://github.com/coleifer/sqlite-web'
arch=('any')
license=('MIT')
depends=('python-flask' 'python-flask' 'python-peewee')
makedepends=('python-setuptools')
source=("https://github.com/coleifer/sqlite-web/archive/0.1.8.tar.gz")
sha512sums=('4afdd5c6a40b8605ecd7f1441aa339131452e762199b559671430681f4d459e7d1f5af80943740851d8c3ac8ed257b7dee5974d796acc65f447e9a74b7fe1fcc')

prepare() {
  cp -r "sqlite-web-$pkgver" "python-sqlite-web-$pkgver"
}

build() {
  cd "$pkgname-$pkgver"

  python setup.py build
}

check() {
  cd "$pkgname-$pkgver"
  python setup.py test
}

package() {
  cd "$pkgname-$pkgver"

  python setup.py install --prefix=/usr --root="$pkgdir" --optimize=1
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}

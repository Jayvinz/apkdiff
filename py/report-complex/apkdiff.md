# APK Diff Report

- 旧版本: `tests/fixtures/complex/v1/v1.apk`
- 新版本: `tests/fixtures/complex/v2/v2.apk`
- 主指标: APK 压缩字节

## 总览

| 指标 | 旧 | 新 | Δ |
| --- | ---: | ---: | ---: |
| APK 文件 | 92.07 KB | 100.00 KB | +7.93 KB |
| 代码 (DEX 归属, 原始) | 96.55 KB | 104.12 KB | +7.57 KB |
| 代码 (DEX 归属, 压缩估算) | 33.12 KB | 35.73 KB | +2.61 KB |
| 资源 (原始) | 68.40 KB | 85.66 KB | +17.26 KB |
| 资源 (压缩) | 49.02 KB | 53.26 KB | +4.24 KB |

## 统计

- 类: 新增 27 / 删除 10 / 修改 32
- 资源: 新增 11 / 删除 5 / 修改 60 / 重命名 1

## 代码类变更

| 状态 | 名称 | 旧 | 新 | Δ |
| --- | --- | ---: | ---: | ---: |
| 新增 | `com.shop.ui.SearchActivity` | 0.00 KB | 0.25 KB | +0.25 KB |
| 删除 | `com.shop.ui.CartActivity` | 0.25 KB | 0.00 KB | -0.25 KB |
| 新增 | `com.shop.ui.adapter.FilterAdapter` | 0.00 KB | 0.21 KB | +0.21 KB |
| 新增 | `com.shop.explore.Adapter` | 0.00 KB | 0.20 KB | +0.20 KB |
| 新增 | `com.shop.explore.Entity` | 0.00 KB | 0.19 KB | +0.19 KB |
| 新增 | `com.shop.explore.ViewModel` | 0.00 KB | 0.15 KB | +0.15 KB |
| 新增 | `com.shop.explore.RepositoryImpl` | 0.00 KB | 0.15 KB | +0.15 KB |
| 删除 | `com.shop.storage.Cache` | 0.13 KB | 0.00 KB | -0.13 KB |
| 新增 | `com.shop.explore.Cache` | 0.00 KB | 0.13 KB | +0.13 KB |
| 新增 | `com.shop.feature.NewFeatureController` | 0.00 KB | 0.12 KB | +0.12 KB |
| 新增 | `com.shop.explore.UseCase` | 0.00 KB | 0.11 KB | +0.11 KB |
| 新增 | `com.shop.explore.Service` | 0.00 KB | 0.11 KB | +0.11 KB |
| 删除 | `com.shop.cart.Validator` | 0.10 KB | 0.00 KB | -0.10 KB |
| 删除 | `com.shop.ui.fragment.ProfileFragment` | 0.10 KB | 0.00 KB | -0.10 KB |
| 删除 | `com.shop.network.Dto` | 0.09 KB | 0.00 KB | -0.09 KB |
| 新增 | `com.shop.analytics.AnalyticsHelper` | 0.00 KB | 0.09 KB | +0.09 KB |
| 新增 | `com.shop.explore.Dto` | 0.00 KB | 0.09 KB | +0.09 KB |
| 删除 | `com.shop.media.Mapper` | 0.09 KB | 0.00 KB | -0.09 KB |
| 新增 | `com.shop.explore.Fragment` | 0.00 KB | 0.09 KB | +0.09 KB |
| 新增 | `com.shop.explore.Validator` | 0.00 KB | 0.09 KB | +0.09 KB |
| 新增 | `com.shop.explore.Utils` | 0.00 KB | 0.09 KB | +0.09 KB |
| 新增 | `com.shop.explore.Mapper` | 0.00 KB | 0.09 KB | +0.09 KB |
| 删除 | `com.shop.social.Event` | 0.08 KB | 0.00 KB | -0.08 KB |
| 删除 | `com.shop.social.Worker` | 0.08 KB | 0.00 KB | -0.08 KB |
| 删除 | `b.d$1` | 0.08 KB | 0.00 KB | -0.08 KB |
| 新增 | `com.shop.explore.Event` | 0.00 KB | 0.08 KB | +0.08 KB |
| 修改 | `com.shop.data.repository.ProductRepositoryImpl` | 0.18 KB | 0.26 KB | +0.08 KB |
| 新增 | `com.shop.explore.Worker` | 0.00 KB | 0.08 KB | +0.08 KB |
| 新增 | `s.h$1` | 0.00 KB | 0.07 KB | +0.07 KB |
| 新增 | `b.e$$ExternalSyntheticLambda0` | 0.00 KB | 0.07 KB | +0.07 KB |
| 新增 | `s.f$$ExternalSyntheticLambda0` | 0.00 KB | 0.07 KB | +0.07 KB |
| 新增 | `s.g$$ExternalSyntheticLambda0` | 0.00 KB | 0.07 KB | +0.07 KB |
| 新增 | `b.e$Holder` | 0.00 KB | 0.06 KB | +0.06 KB |
| 删除 | `b.d$Holder` | 0.06 KB | 0.00 KB | -0.06 KB |
| 修改 | `com.shop.app.ShopApplication` | 0.19 KB | 0.25 KB | +0.06 KB |
| 修改 | `com.shop.domain.model.Product` | 0.38 KB | 0.43 KB | +0.06 KB |
| 新增 | `s.g$Holder` | 0.00 KB | 0.05 KB | +0.05 KB |
| 新增 | `s.h$Holder` | 0.00 KB | 0.05 KB | +0.05 KB |
| 修改 | `com.shop.ui.MainActivity` | 0.33 KB | 0.38 KB | +0.05 KB |
| 修改 | `com.shop.util.MoneyFormatter` | 0.09 KB | 0.14 KB | +0.05 KB |
| 新增 | `s.a$-CC` | 0.00 KB | 0.04 KB | +0.04 KB |
| 修改 | `com.shop.user.Entity` | 0.19 KB | 0.23 KB | +0.04 KB |
| 新增 | `com.shop.explore.Repository` | 0.00 KB | 0.03 KB | +0.03 KB |
| 修改 | `com.shop.push.Adapter` | 0.21 KB | 0.23 KB | +0.02 KB |
| 修改 | `com.shop.checkout.Adapter` | 0.21 KB | 0.24 KB | +0.02 KB |
| 修改 | `com.shop.catalog.ViewModel` | 0.20 KB | 0.22 KB | +0.02 KB |
| 修改 | `com.shop.social.ViewModel` | 0.16 KB | 0.18 KB | +0.02 KB |
| 修改 | `com.shop.analytics.Entity` | 0.30 KB | 0.32 KB | +0.02 KB |
| 修改 | `com.shop.catalog.Cache` | 0.20 KB | 0.22 KB | +0.02 KB |
| 修改 | `com.shop.checkout.Dto` | 0.10 KB | 0.12 KB | +0.02 KB |
| 修改 | `com.shop.checkout.UseCase` | 0.12 KB | 0.14 KB | +0.02 KB |
| 修改 | `com.shop.push.UseCase` | 0.11 KB | 0.13 KB | +0.02 KB |
| 修改 | `com.shop.social.Cache` | 0.14 KB | 0.16 KB | +0.02 KB |
| 修改 | `com.shop.checkout.Service` | 0.12 KB | 0.14 KB | +0.02 KB |
| 修改 | `com.shop.push.Dto` | 0.10 KB | 0.12 KB | +0.02 KB |
| 修改 | `com.shop.push.Service` | 0.11 KB | 0.13 KB | +0.02 KB |
| 修改 | `com.shop.user.Mapper` | 0.11 KB | 0.12 KB | +0.02 KB |
| 修改 | `com.shop.user.Worker` | 0.10 KB | 0.11 KB | +0.02 KB |
| 修改 | `com.shop.network.Cache` | 0.13 KB | 0.15 KB | +0.01 KB |
| 修改 | `com.shop.analytics.Worker` | 0.09 KB | 0.10 KB | +0.01 KB |
| 修改 | `com.shop.helper.Mapper` | 0.09 KB | 0.10 KB | +0.01 KB |
| 修改 | `com.shop.helper.Worker` | 0.08 KB | 0.09 KB | +0.01 KB |
| 修改 | `com.shop.ui.Dto` | 0.09 KB | 0.11 KB | +0.01 KB |
| 修改 | `com.shop.ui.Service` | 0.11 KB | 0.12 KB | +0.01 KB |
| 修改 | `com.shop.analytics.Mapper` | 0.11 KB | 0.12 KB | +0.01 KB |
| 修改 | `com.shop.ui.Adapter` | 0.20 KB | 0.21 KB | +0.01 KB |
| 修改 | `com.shop.ui.UseCase` | 0.11 KB | 0.12 KB | +0.01 KB |
| 修改 | `com.shop.network.ViewModel` | 0.16 KB | 0.17 KB | +0.01 KB |
| 修改 | `com.shop.helper.Entity` | 0.19 KB | 0.20 KB | +0.01 KB |

## 资源文件变更

| 状态 | 名称 | 旧 | 新 | Δ |
| --- | --- | ---: | ---: | ---: |
| 新增 | `lib/mips/libshop.so` | 0.00 KB | 4.69 KB | +4.69 KB |
| 删除 | `lib/armeabi-v7a/libshop.so` | 3.81 KB | 0.00 KB | -3.81 KB |
| 修改 | `resources.arsc` | 11.90 KB | 12.97 KB | +1.07 KB |
| 修改 | `lib/arm64-v8a/libshop.so` | 8.01 KB | 8.79 KB | +0.78 KB |
| 新增 | `res/layout/activity_search.xml` | 0.00 KB | 0.31 KB | +0.31 KB |
| 新增 | `res/layout/item_explore.xml` | 0.00 KB | 0.30 KB | +0.30 KB |
| 新增 | `assets/databases/explore.db` | 0.00 KB | 0.30 KB | +0.30 KB |
| 修改 | `lib/arm64-v8a/libshop_core.so` | 5.67 KB | 5.96 KB | +0.29 KB |
| 新增 | `res/drawable/bg_explore.xml` | 0.00 KB | 0.23 KB | +0.23 KB |
| 删除 | `res/layout/fragment_home.xml` | 0.22 KB | 0.00 KB | -0.22 KB |
| 新增 | `res/drawable/bg_accent.xml` | 0.00 KB | 0.19 KB | +0.19 KB |
| 删除 | `assets/images/legacy.svg` | 0.15 KB | 0.00 KB | -0.15 KB |
| 新增 | `assets/images/explore.svg` | 0.00 KB | 0.14 KB | +0.14 KB |
| 新增 | `res/raw/explore_config.json` | 0.00 KB | 0.07 KB | +0.07 KB |
| 删除 | `assets/web/index.html` | 0.05 KB | 0.00 KB | -0.05 KB |
| 删除 | `res/raw/legal_notice.txt` | 0.05 KB | 0.00 KB | -0.05 KB |
| 新增 | `assets/nested/ui/new_pref.json` | 0.00 KB | 0.05 KB | +0.05 KB |
| 新增 | `assets/explore/config.json` | 0.00 KB | 0.05 KB | +0.05 KB |
| 修改 | `assets/app-config.json` | 0.05 KB | 0.07 KB | +0.02 KB |
| 新增 | `res/raw/help.txt` | 0.00 KB | 0.02 KB | +0.02 KB |
| 修改 | `res/layout/activity_main.xml` | 0.34 KB | 0.35 KB | +0.01 KB |
| 修改 | `AndroidManifest.xml` | 0.55 KB | 0.56 KB | +0.00 KB |
| 修改 | `res/raw/catalog.bin` | 0.02 KB | 0.02 KB | +0.00 KB |
| 修改 | `assets/images/hero.svg` | 0.18 KB | 0.18 KB | +0.00 KB |
| 修改 | `res/drawable/bg_checkout.xml` | 0.23 KB | 0.23 KB | -0.00 KB |
| 修改 | `res/drawable/bg_media.xml` | 0.23 KB | 0.23 KB | -0.00 KB |
| 修改 | `res/drawable/bg_network.xml` | 0.23 KB | 0.24 KB | +0.00 KB |
| 修改 | `res/drawable/bg_push.xml` | 0.23 KB | 0.23 KB | +0.00 KB |
| 修改 | `res/drawable/bg_ui.xml` | 0.23 KB | 0.23 KB | -0.00 KB |
| 修改 | `res/layout/item_helper.xml` | 0.30 KB | 0.30 KB | +0.00 KB |
| 修改 | `res/layout/item_media.xml` | 0.30 KB | 0.30 KB | -0.00 KB |
| 修改 | `res/layout/item_network.xml` | 0.30 KB | 0.30 KB | +0.00 KB |
| 修改 | `res/layout/item_ui.xml` | 0.29 KB | 0.29 KB | +0.00 KB |
| 修改 | `res/layout/item_user.xml` | 0.29 KB | 0.30 KB | +0.00 KB |
| 修改 | `res/raw/logo.svg` | 0.14 KB | 0.14 KB | +0.00 KB |
| 重命名 | `res/raw/settings.json` ← `res/raw/config.json` | 0.09 KB | 0.09 KB | 0.00 KB |
| 修改 | `assets/analytics/config.json` | 0.05 KB | 0.05 KB | 0.00 KB |
| 修改 | `assets/cart/config.json` | 0.04 KB | 0.04 KB | 0.00 KB |
| 修改 | `assets/catalog/config.json` | 0.05 KB | 0.05 KB | 0.00 KB |
| 修改 | `assets/checkout/config.json` | 0.05 KB | 0.05 KB | 0.00 KB |
| 修改 | `assets/databases/app.db` | 0.21 KB | 0.21 KB | 0.00 KB |
| 修改 | `assets/helper/config.json` | 0.04 KB | 0.04 KB | 0.00 KB |
| 修改 | `assets/media/config.json` | 0.04 KB | 0.04 KB | 0.00 KB |
| 修改 | `assets/network/config.json` | 0.05 KB | 0.05 KB | 0.00 KB |
| 修改 | `assets/push/config.json` | 0.04 KB | 0.04 KB | 0.00 KB |
| 修改 | `assets/social/config.json` | 0.04 KB | 0.04 KB | 0.00 KB |
| 修改 | `assets/storage/config.json` | 0.05 KB | 0.05 KB | 0.00 KB |
| 修改 | `assets/ui/config.json` | 0.04 KB | 0.04 KB | 0.00 KB |
| 修改 | `assets/user/config.json` | 0.04 KB | 0.04 KB | 0.00 KB |
| 修改 | `res/drawable/bg_analytics.xml` | 0.24 KB | 0.24 KB | 0.00 KB |
| 修改 | `res/drawable/bg_cart.xml` | 0.23 KB | 0.23 KB | 0.00 KB |
| 修改 | `res/drawable/bg_catalog.xml` | 0.23 KB | 0.23 KB | 0.00 KB |
| 修改 | `res/drawable/bg_helper.xml` | 0.23 KB | 0.23 KB | 0.00 KB |
| 修改 | `res/drawable/bg_social.xml` | 0.23 KB | 0.23 KB | 0.00 KB |
| 修改 | `res/drawable/bg_storage.xml` | 0.24 KB | 0.24 KB | 0.00 KB |
| 修改 | `res/drawable/bg_user.xml` | 0.23 KB | 0.23 KB | 0.00 KB |
| 修改 | `res/layout/item_analytics.xml` | 0.30 KB | 0.30 KB | 0.00 KB |
| 修改 | `res/layout/item_cart.xml` | 0.29 KB | 0.29 KB | 0.00 KB |
| 修改 | `res/layout/item_catalog.xml` | 0.30 KB | 0.30 KB | 0.00 KB |
| 修改 | `res/layout/item_checkout.xml` | 0.30 KB | 0.30 KB | 0.00 KB |
| 修改 | `res/layout/item_product.xml` | 0.28 KB | 0.28 KB | 0.00 KB |
| 修改 | `res/layout/item_push.xml` | 0.29 KB | 0.29 KB | 0.00 KB |
| 修改 | `res/layout/item_social.xml` | 0.30 KB | 0.30 KB | 0.00 KB |
| 修改 | `res/layout/item_storage.xml` | 0.30 KB | 0.30 KB | 0.00 KB |
| 修改 | `res/mipmap-xxhdpi-v4/ic_launcher.png` | 0.07 KB | 0.07 KB | 0.00 KB |
| 修改 | `res/raw/analytics_config.json` | 0.07 KB | 0.07 KB | 0.00 KB |
| 修改 | `res/raw/cart_config.json` | 0.07 KB | 0.07 KB | 0.00 KB |
| 修改 | `res/raw/catalog_config.json` | 0.07 KB | 0.07 KB | 0.00 KB |
| 修改 | `res/raw/checkout_config.json` | 0.07 KB | 0.07 KB | 0.00 KB |
| 修改 | `res/raw/helper_config.json` | 0.07 KB | 0.07 KB | 0.00 KB |
| 修改 | `res/raw/media_config.json` | 0.07 KB | 0.07 KB | 0.00 KB |
| 修改 | `res/raw/network_config.json` | 0.07 KB | 0.07 KB | 0.00 KB |
| 修改 | `res/raw/push_config.json` | 0.07 KB | 0.07 KB | 0.00 KB |
| 修改 | `res/raw/social_config.json` | 0.07 KB | 0.07 KB | 0.00 KB |
| 修改 | `res/raw/storage_config.json` | 0.07 KB | 0.07 KB | 0.00 KB |
| 修改 | `res/raw/ui_config.json` | 0.07 KB | 0.07 KB | 0.00 KB |
| 修改 | `res/raw/user_config.json` | 0.07 KB | 0.07 KB | 0.00 KB |
